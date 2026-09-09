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

# 初始化并发流控信号量（硬控在您规定的 8 并发以内）
qps_semaphore = asyncio.Semaphore(8)

# 财务核心关键字分水岭
KEYWORDS = ["当前状态", "付款状态", "转账说明", "当前状态", "支付时间", "转账时间", "收款时间", "支付方式", "交易单号", "转账单号", "商户全称", "商户单号", "收单机构", "商品", "账单服务"]

def format_date_time(raw_datetime_str):
    """
    ⚡ 日期时间提取归一器
    """
    match = re.match(r'(\d+)年(\d+)月(\d+)日(\d+:\d+:\d+)', raw_datetime_str)
    if match:
        year, month, day, hms = match.groups()
        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
        return date_str, f"{date_str} {hms}"
    return "", ""

def get_sn_multiline_value(texts, scores, start_idx):
    """
    ⚡ 单号多行级联拼接无缝嗅探函数
    """
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
async def async_ocr_request(image_path, secret_id, secret_key, action_name):
    """
    ⚡ 异步高并发调度网关
    """
    async with qps_semaphore:  
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync_tencent_ocr, image_path, secret_id, secret_key, action_name)
        except TencentCloudSDKException as err:
            # AuthFailure.SecretIdNotFound 用来测试账号资源使用完了，切换账号的情况
            exhausted_codes = [
                "LimitExceeded", 
                "ResourceInsufficient", 
                # "AuthFailure.SecretIdNotFound",
                "ResourceUnavailable.ResourcePackageRunOut"
            ]
            if err.code in exhausted_codes or any(k in err.message for k in ["停机", "欠费", "次数", "耗尽", "余额不足"]):
                raise ValueError("ENGINE_EXHAUSTED")
            raise err
        except Exception as e:
            raise e

def _sync_tencent_ocr(image_path, secret_id, secret_key, action_name):
    """
    ⚡ 底层腾讯云原生官方 API 物理握手交互（锁定原生 endpoint 官方域名，拒绝魔改）
    """
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
        
    cred = credential.Credential(secret_id, secret_key)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "ocr.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    client = ocr_client.OcrClient(cred, "", clientProfile)
    
    if action_name == "GeneralAccurateOCR":
        req = models.GeneralAccurateOCRRequest()
        req.ImageBase64 = image_base64
        resp = client.GeneralAccurateOCR(req)
    else:
        req = models.GeneralBasicOCRRequest()
        req.ImageBase64 = image_base64
        resp = client.GeneralBasicOCR(req)
    
    response_json = json.loads(resp.to_json_string())
    image_results = []
    if "TextDetections" in response_json:
        for idx, item in enumerate(response_json["TextDetections"]):
            text = item["DetectedText"].strip()
            confidence = item["Confidence"] / 100.0
            if text:
                # 🎯 全链别名优化：有且仅在返回数组的第一条数据尾部打上引擎透传标签
                if idx == 0:
                    image_results.append(f"{text}||||||{confidence:.2f}||||||{action_name}")
                else:
                    image_results.append(f"{text}||||||{confidence:.2f}")
    return image_results
def clean_and_parse_ocr(img_name, img_list, conf_threshold=0.99):
    """
    ⚡ 结构化数据脱敏、比对与多层漏斗金字塔业务匹配洗盘内核
    """
    used_engine = "GeneralBasicOCR"
    if img_list:
        # 🎯 精准锁死索引，防止处理列表第一项标签时引发类型冲突
        first_item_parts = img_list[0].split("||||||")
        if len(first_item_parts) > 2:
            used_engine = first_item_parts[2]
            img_list[0] = f"{first_item_parts[0]}||||||{first_item_parts[1]}"

    texts = []
    scores = []
    
    # 🎯 核心修复：原地清洗并同步压入 texts 与 scores，确保两者下标百分之百完全对齐
    for item in img_list:
        parts = item.split("||||||")
        raw_txt = parts[0] if len(parts) > 0 else "" 
        clean_txt = raw_txt.replace(" ", "").replace("\t", "").replace("\xa0", "").strip().replace("①", "")
        if clean_txt == "": continue
        
        texts.append(clean_txt)
        
        raw_score = float(parts[1]) if len(parts) > 1 else 1.0
        if used_engine == "GeneralAccurateOCR":
            final_score = 1.0 if raw_score >= conf_threshold else raw_score
        else:
            final_score = raw_score
        scores.append(final_score)   
        
    res_map = {}
    amount_idx = -1
    for i, t in enumerate(texts):
        if (t.startswith("-") or t.startswith("+")) and re.match(r'^[-+][0-9.]+$', t):
            # 🎯 此时 texts 与 scores 下标完全绝对一致，绝不可能再发生越界引发的卡死
            res_map["付款金额"] = (t, scores[i])
            amount_idx = i
            break
   
    res_map = {}
    amount_idx = -1
    for i, t in enumerate(texts):
        if (t.startswith("-") or t.startswith("+")) and re.match(r'^[-+][0-9.]+$', t):
            res_map["付款金额"] = (t, scores[i])
            amount_idx = i
            break

    btn_found_idx = -1
    matched_keyword = None
    
    if amount_idx > 0:
        # 👑 【第一级最高优先级】：在付款金额上方，优先搜索“扫二维码付款”或“转账-”开头的行
        PRIO_1_KEYWORDS = ["扫二维码付款", "转账-"]
        for i in range(0, amount_idx):
            current_text = texts[i]
            for kw in PRIO_1_KEYWORDS:
                if current_text.startswith(kw):
                    btn_found_idx = i
                    matched_keyword = kw
                    break
            if btn_found_idx != -1: break
            
        # 🥈 【第二级降级优先级】：第一级落空时，才去搜索“全部账单”、“x”等按钮标志物
        if btn_found_idx == -1:
            PRIO_2_KEYWORDS = ["全部账单", "X全部账单", "x全部账单", "X", "x"]
            for i in range(0, amount_idx):
                current_text = texts[i]
                if current_text in PRIO_2_KEYWORDS:
                    btn_found_idx = i
                    matched_keyword = current_text
                    break
                for kw in PRIO_2_KEYWORDS:
                    if current_text.startswith(kw):
                        btn_found_idx = i
                        matched_keyword = kw
                        break
                if btn_found_idx != -1: break

    # 执行收款官方跨行级联拼接数据汇整
    official_val = ""
    official_sc = 1.0
    
    if amount_idx > 0:
        if btn_found_idx != -1:
            # 命中第一级或第二级分水岭
            collected_official_texts = []
            collected_official_scores = []
            
            first_line_text = texts[btn_found_idx]
            
            # 🎯 核心逻辑校准：如果是“扫二维码付款”或“转账-”，作为极其重要类型前缀必须保留输出！
            if matched_keyword in ["扫二维码付款", "转账-"]:
                collected_official_texts.append(first_line_text)
                collected_official_scores.append(scores[btn_found_idx])
            else:
                # 针对第二级（全部账单等界面UI噪音）执行剥离过滤
                if first_line_text != matched_keyword:
                    cleaned_tail = first_line_text[len(matched_keyword):].strip()
                    if cleaned_tail and cleaned_tail not in ["全部账单", "X", "x"] and not any(cleaned_tail.startswith(k) for k in ["全部账单", "X", "x"]):
                        if cleaned_tail not in KEYWORDS and not any(k in cleaned_tail for k in KEYWORDS):
                            collected_official_texts.append(cleaned_tail)
                            collected_official_scores.append(scores[btn_found_idx])
            
            # 向下连卷包裹到付款金额之间的跨行商家文本
            for idx in range(btn_found_idx + 1, amount_idx):
                next_t = texts[idx]
                if next_t in ["全部账单", "X", "x"] or any(next_t.startswith(kw) for kw in ["全部账单", "X", "x"]): continue
                if next_t in KEYWORDS or any(k in next_t for k in KEYWORDS): break
                collected_official_texts.append(next_t)
                collected_official_scores.append(scores[idx])
                
            if collected_official_texts:
                official_val = "".join(collected_official_texts)
                # 🎯 降维机制：多行时取其中的【最低置信度】，消除 List 格式化崩溃
                official_sc = min(collected_official_scores) if collected_official_scores else 1.0
                
        else:
            # 🥉 【第三级绝对保底】：前两级标志物均未发现，自动抓取付款金额正上方紧挨着的那一行数据
            prev_idx = amount_idx - 1
            if prev_idx >= 0:
                prev_txt = texts[prev_idx]
                if prev_txt not in ["全部账单", "X", "x"] and not (prev_txt in KEYWORDS or any(k in prev_txt for k in KEYWORDS)):
                    official_val = prev_txt
                    official_sc = scores[prev_idx]

    if official_val:
        res_map["收款官方"] = (official_val, official_sc)

    # 捕捉其余维度的基础账单元数据
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

    # 🎯 先用后付强行硬核拦截线：向落盘矩阵回填前的最终关卡！
    # 只要收款官方字样中包含了“先用后付”，不管左侧有什么粘连杂质(如 LA)，强制一刀切重写，并给予 1.0 绝对置信度
    o_val, o_sc = res_map.get("收款官方", ("", 1.0))
    if "先用后付" in o_val: 
        res_map["收款官方"] = ("先用后付", 1.0)

    # 🎯 【核心修改部分】：在落盘生成二维矩阵前，执行最高优先级的付款方式硬核拦截净化
    # 只要付款方式字样中包含了“零钱通”，不管后面带有任何长尾、尾号和括号残留，强制清洗为纯净版
    m_val, m_sc = res_map.get("付款方式", ("", 1.0))
    if "零钱通" in m_val:
        res_map["付款方式"] = ("零钱通", 1.0)


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
