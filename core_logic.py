import os
import re
import base64
import json
import asyncio
import warnings
from datetime import datetime
import pandas as pd
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ocr.v20181119 import ocr_client, models
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException

warnings.filterwarnings("ignore", category=UserWarning)

# 初始化限流信号量：严防死守 10 QPS，设置为 8 预留安全缓冲
qps_semaphore = asyncio.Semaphore(8)

KEYWORDS = ["当前状态", "付款状态", "转账说明", "当前状态", "支付时间", "转账时间", "收款时间", "支付方式", "交易单号", "转账单号", "商户全称", "商户单号", "收单机构", "商品", "账单服务"]

def format_date_time(raw_datetime_str):
    """提取标准日期与时间"""
    match = re.match(r'(\d+)年(\d+)月(\d+)日(\d+:\d+:\d+)', raw_datetime_str)
    if match:
        year, month, day, hms = match.groups()
        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
        return date_str, f"{date_str} {hms}"
    return "", ""

def get_sn_multiline_value(texts, scores, start_idx):
    """单号类专用无缝嗅探拼接函数"""
    if start_idx >= len(texts): return "", 1.0
    collected_text = texts[start_idx]
    collected_scores = [scores[start_idx]]
    current_idx = start_idx + 1
    while current_idx < len(texts):
        next_t = texts[current_idx]
        if next_t in KEYWORDS or any(k in next_t for k in KEYWORDS): break
        if (next_t.startswith("-") or next_t.startswith("+")) and re.match(r'^[-+][0-9.]+$', next_t): break
        if re.match(r'^[0-9a-zA-Z等]+$', next_t):
            collected_text += next_t
            collected_scores.append(scores[current_idx])
            current_idx += 1
        else:
            break
    final_score = 1.0
    for s in collected_scores:
        if s != 1.0:
            final_score = s
            break
    return collected_text, final_score

async def async_ocr_request(image_path, secret_id, secret_key):
    """
    异步并发 OCR 核心，带严格 QPS 限流控制
    """
    async with qps_semaphore:  
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_tencent_ocr, image_path, secret_id, secret_key)
        except TencentCloudSDKException as err:
            # AuthFailure.SecretIdNotFound 这个异常是做测试用的，实际上应该是：ResourceUnavailable.ResourcePackageRunOut
            exhausted_codes = [
                "LimitExceeded", 
                "ResourceInsufficient", 
                "AuthFailure.SecretIdNotFound",
                "ResourceUnavailable.ResourcePackageRunOut"
            ]
            if err.code in exhausted_codes or any(k in err.message for k in ["停机", "欠费", "次数", "耗尽", "余额不足"]):
                raise ValueError("ACCOUNT_EXHAUSTED")
            raise err
        except Exception as e:
            raise e

def _sync_tencent_ocr(image_path, secret_id, secret_key):
    """底层被包装的腾讯云物理调用"""
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
        
    cred = credential.Credential(secret_id, secret_key)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "ocr.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    client = ocr_client.OcrClient(cred, "", clientProfile)
    
    req = models.GeneralBasicOCRRequest()
    req.ImageBase64 = image_base64
    resp = client.GeneralBasicOCR(req)
    
    response_json = json.loads(resp.to_json_string())
    image_results = []
    if "TextDetections" in response_json:
        for item in response_json["TextDetections"]:
            text = item["DetectedText"].strip()
            confidence = item["Confidence"] / 100.0
            if text:
                image_results.append(f"{text}||||||{confidence:.2f}")
    return image_results

def clean_and_parse_ocr(img_name, img_list):
    """深度解析逻辑"""
    texts = []
    scores = []
    for item in img_list:
        parts = item.split("||||||")
        raw_txt = parts[0] if len(parts) > 0 else "" 
        clean_txt = raw_txt.replace(" ", "").replace("\t", "").replace("\xa0", "").strip().replace("①", "")
        if clean_txt == "": continue
        texts.append(clean_txt)
        scores.append(float(parts[1]) if len(parts) > 1 else 1.0)   
        
    res_map = {}
    for i, t in enumerate(texts):
        if (t.startswith("-") or t.startswith("+")) and re.match(r'^[-+][0-9.]+$', t):
            res_map["付款金额"] = (t, scores[i])
            break
            
    amount_idx = -1
    for i, t in enumerate(texts):
        if (t.startswith("-") or t.startswith("+")) and re.match(r'^[-+][0-9.]+$', t):
            amount_idx = i
            break

    btn_found_idx = -1
    for i, t in enumerate(texts):
        if t in ["全部账单", "X", "x", "X全部账单", "x全部账单"]:
            btn_found_idx = i
            break

    if btn_found_idx != -1 and amount_idx != -1 and amount_idx > btn_found_idx:
        collected_official_texts = []
        collected_official_scores = []
        for idx in range(btn_found_idx + 1, amount_idx):
            next_t = texts[idx]
            if next_t in KEYWORDS or any(k in next_t for k in KEYWORDS):
                break
            collected_official_texts.append(next_t)
            collected_official_scores.append(scores[idx])
            
        if collected_official_texts:
            res_map["收款官方"] = ("".join(collected_official_texts), collected_official_scores[0])

    elif amount_idx > 0:
        prev_idx = amount_idx - 1
        prev_txt = texts[prev_idx]
        if prev_txt not in ["全部账单", "X", "x", "X全部账单", "x全部账单"] and not (prev_txt in KEYWORDS or any(k in prev_txt for k in KEYWORDS)):
            res_map["收款官方"] = (prev_txt, scores[prev_idx])

    for i, t in enumerate(texts):
        if i + 1 >= len(texts): continue
        next_val = texts[i+1]
        next_score = scores[i+1]

        if "当前状态" in t: 
            res_map["付款状态"] = (next_val, next_score)
        elif "支付时间" in t or "转账时间" in t:
            date_p, time_p = format_date_time(next_val)
            res_map["采购日期"] = (date_p, next_score)
            res_map["支付日期"] = (date_p, next_score)
            res_map["支付时间"] = (time_p, next_score)
        elif "支付方式" in t or "支付方式" in t.replace(" ", ""):
            res_map["付款方式"] = (next_val, 1.0 if "零钱通" in next_val else next_score)
        elif "商户全称" in t: 
            res_map["商户全称"] = (next_val, next_score)
        elif "交易单号" in t or "转账单号" in t:  
            val, sc = get_sn_multiline_value(texts, scores, i + 1)
            res_map["交易单号"] = (val, sc)
        elif "商户单号" in t: 
            val, sc = get_sn_multiline_value(texts, scores, i + 1)
            res_map["商户单号"] = (val, sc)

    official_val, official_sc = res_map.get("收款官方", ("", 1.0))
    if "先用后付" in official_val: res_map["收款官方"] = ("先用后付", 1.0)
    
    row_dict = {"图片名称": img_name}
    paired_keys = ["采购日期", "付款状态", "收款官方", "付款金额", "支付日期", "支付时间", "付款方式", "交易单号", "商户全称", "商户单号"]
    for col_name in paired_keys:
        val, sc = res_map.get(col_name, ("", 1.0))
        row_dict[col_name] = val
        conf_val = "" if sc == 1.0 else f"{sc:.2f}"
        row_dict[f"{col_name}_sc"] = conf_val
        row_dict[f"{col_name}_置信度"] = conf_val
        
    row_dict["系统记账日期"] = ""
    row_dict["采购对账单号"] = ""
    return row_dict
