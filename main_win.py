import os
import sys
import time
import json
import threading
import asyncio
import re
import tkinter as tk
from tkinter import filedialog, ttk
import pandas as pd
from datetime import datetime

# 引入异步调用与清洗内核
import core_logic
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PATH_CONFIG_FILE = os.path.join(BASE_DIR, '.ocr_path_config.txt')
CRED_CONFIG_FILE = os.path.join(BASE_DIR, '.ocr_credentials_secret.json')
BASE_ENGINE_FILE = os.path.join(BASE_DIR, 'base_engine.json')
class CustomDialog(tk.Toplevel):
    """
    ⚡ 全自定义高颜值 Tkinter 弹窗（集成文件夹失败高阶滚动列表与防闪烁黑科技）
    """
    def __init__(self, parent, title, message, mode="info", callback_action=None, btn_action_text=" 确 定 ", folder_list=None):
        super().__init__(parent)
        
        # 🛡️ 核心防闪：立刻让窗口进入全隐身透明状态
        self.attributes("-alpha", 0.0) 
        
        self.title(title)
        self.configure(bg="#F3F3F3")
        self.resizable(False, False)
        # 开启强制模态聚焦机制
        self.transient(parent)
        self.grab_set()

        # 根据模式动态配置视觉主题颜色与高亮
        theme_color = "#0078D4" if mode == "info" else "#D47A00" if mode == "warning" else "#E81123"
        
        # 📐 精密屏幕居中坐标推算
        dialog_width, dialog_height = 480, 260 if not folder_list else 340
        
        main_w = parent.winfo_width()
        main_h = parent.winfo_height()
        main_x = parent.winfo_x()
        main_y = parent.winfo_y()
        pos_x = main_x + (main_w - dialog_width) // 2
        pos_y = main_y + (main_h - dialog_height) // 2
        self.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        # ✍️ 核心文字与组件渲染布局
        main_frame = tk.Frame(self, bg="#F3F3F3", padx=25, pady=15)
        main_frame.pack(fill="both", expand=True)

        lbl_title = tk.Label(main_frame, text=title, font=("微软雅黑", 12, "bold"), fg=theme_color, bg="#F3F3F3")
        lbl_title.pack(anchor="w", pady=(0, 6))

        lbl_msg = tk.Label(main_frame, text=message, font=("微软雅黑", 10), justify="left", fg="#333333", bg="#F3F3F3", wraplength=430)
        lbl_msg.pack(anchor="w", pady=(2, 6))
        # 如果传入了失败文件夹列表，则动态渲染一个现代化的带滚动条列表
        if folder_list:
            list_frame = tk.Frame(main_frame, bg="#F3F3F3")
            list_frame.pack(fill="both", expand=True, pady=(2, 2))
            
            scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            box = tk.Listbox(list_frame, font=("微软雅黑", 9), fg="#555555", bg="white", 
                             yscrollcommand=scrollbar.set, highlightthickness=1, highlightcolor="#CCCCCC", height=5)
            box.pack(side=tk.LEFT, fill="both", expand=True)
            scrollbar.config(command=box.yview)
            
            for f_path in folder_list:
                box.insert(tk.END, f" 📂 {f_path}")
        # 🔘 底部通用操作控制区域
        btn_frame = tk.Frame(self, pady=12, bg="#F3F3F3")
        btn_frame.pack(fill="x", side="bottom")

        if callback_action:
            btn_action = tk.Button(btn_frame, text=btn_action_text, font=("微软雅黑", 10, "bold"), bg="#107C41", fg="white", padx=15, pady=3,
                                   command=lambda: [callback_action(), self.destroy()])
            btn_action.pack(side="right", padx=(10, 25))
            
            btn_cancel = tk.Button(btn_frame, text=" 取 消 ", font=("微软雅黑", 10), bg="#E1E1E1", fg="#333333", padx=15, pady=3, command=self.destroy)
            btn_cancel.pack(side="right")
        else:
            btn_close = tk.Button(btn_frame, text=" 关 闭 ", font=("微软雅黑", 10), bg=theme_color, fg="white", padx=20, pady=3, command=self.destroy)
            btn_close.pack(side="right", padx=25)

        # 🚀 现身时刻：解除透明锁
        self.attributes("-alpha", 1.0)
        self.attributes("-topmost", True)
class BillOcrGui:
    def __init__(self, window):
        self.window = window
        self.window.title("⚡ 微信支付图片多账号多引擎智能轮询对账系统 v2.2")
        self.window.geometry("640x630")
        self.window.resizable(False, False)
        
        # 1. 🔑 密钥配置面板
        frame_cred = tk.LabelFrame(window, text=" 🔐 企业微信 OCR 凭证批量配置 ", font=("微软雅黑", 9, "bold"), padx=10, pady=8)
        frame_cred.pack(fill="x", padx=25, pady=8)
        
        lbl_tip = tk.Label(frame_cred, text="格式: SecretId:xxx 换行 SecretKey:sss (双引擎依次轮询使用)", font=("微软雅黑", 8), fg="gray")
        lbl_tip.pack(anchor="w")
        
        self.txt_cred = tk.Text(frame_cred, height=6, width=65, font=("Consolas", 9))
        self.txt_cred.pack(pady=5, side=tk.LEFT, fill="x", expand=True)
        
        btn_save_cred = tk.Button(frame_cred, text="💾 保存\n配置", command=self.save_credentials, bg="#107C41", fg="white", font=("微软雅黑", 10, "bold"), width=6)
        btn_save_cred.pack(side=tk.RIGHT, padx=5, fill="y", pady=5)
        # 2. 文件夹路径选择面板
        frame_dir = tk.Frame(window, pady=10)
        frame_dir.pack(fill="x", padx=25)
        tk.Label(frame_dir, text="图片文件夹:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.entry_path = tk.Entry(frame_dir, width=42, font=("微软雅黑", 10))
        self.entry_path.pack(side=tk.LEFT, padx=10)
        tk.Button(frame_dir, text=" 浏览... ", command=self.select_folder, bg="#E1E1E1").pack(side=tk.LEFT)

        # 3. 📊 实时高并发执行进度面板
        self.frame_progress = tk.LabelFrame(window, text=" 📊 实时多账户多引擎轮询流控进度 ", font=("微软雅黑", 9, "bold"), padx=15, pady=8)
        self.frame_progress.pack(fill="x", padx=25, pady=5)
        
        self.label_counter = tk.Label(self.frame_progress, text="等待启动...", font=("微软雅黑", 10))
        self.label_counter.pack(anchor="w")
        self.label_eta = tk.Label(self.frame_progress, text="正在运转的引擎: --", font=("微软雅黑", 10), fg="#004B87")
        self.label_eta.pack(anchor="w", pady=(2, 5))
        
        self.progress_bar = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x")
        self.label_status = tk.Label(window, text="💡 状态: 准备就绪。优先使用普通版，超额自动切至高精度版！", font=("微软雅黑", 10), fg="#333333", pady=3)
        self.label_status.pack()

        # 4. 🚀 启动大按钮与合规免责声明
        self.btn_start = tk.Button(window, text="🚀 启动云端高并发对账", command=self.start_async_thread, font=("微软雅黑", 12, "bold"), bg="#0078D4", fg="white", width=25, height=2)
        self.btn_start.pack(pady=5)

        frame_disclaimer = tk.LabelFrame(window, text=" ⚖️ 法律与合规免责声明 ", font=("微软雅黑", 9, "bold"), fg="#D47A00", padx=10, pady=5)
        frame_disclaimer.pack(fill="x", padx=25, pady=5)
        disclaimer_text = "提示：本工具仅限内部对账提效比对使用。双引擎动态轮询需确保名下所有账号处于授权状态。操作方应自行承担明文存储密钥导致的安全资产风险。"
        lbl_disc = tk.Label(frame_disclaimer, text=disclaimer_text, font=("微软雅黑", 8), fg="#666666", wraplength=550, justify="left")
        lbl_disc.pack()

        self.load_history_config()
    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            clean_dir = os.path.normpath(folder_selected)
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, clean_dir)
            try:
                with open(PATH_CONFIG_FILE, "w", encoding="utf-8") as f: f.write(clean_dir)
            except: pass

    def load_history_config(self):
        if os.path.exists(PATH_CONFIG_FILE):
            try:
                with open(PATH_CONFIG_FILE, "r", encoding="utf-8") as f:
                    p = f.read().strip()
                    if os.path.exists(p): self.entry_path.insert(0, p)
            except: pass
        if os.path.exists(CRED_CONFIG_FILE):
            try:
                with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                    accounts = json.load(f)
                accounts = self.check_and_reset_monthly(accounts)
                
                text_show = ""
                for acc in accounts:
                    engine_states = acc.get("engine_status", {})
                    b_status = " [普通版用尽]" if engine_states.get("GeneralBasicOCR") == "exhausted" else ""
                    a_status = " [高精度用尽]" if engine_states.get("GeneralAccurateOCR") == "exhausted" else ""
                    text_show += f"SecretId:{acc['secret_id']}{b_status}{a_status}\nSecretKey:{acc['secret_key']}\n\n"
                self.txt_cred.insert("1.0", text_show.strip())
            except: pass
    def check_and_reset_monthly(self, accounts):
        """
        🔒 绝对跨月保护锁：
        全面升级至引擎级细粒度监测，严禁当月周期内发生错误恢复。
        """
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        need_save = False
        
        for acc in accounts:
            if "engine_status" not in acc:
                acc["engine_status"] = {"GeneralBasicOCR": "valid", "GeneralAccurateOCR": "valid"}
                need_save = True
                
            last_used_str = acc.get("last_used", "").strip()
            if last_used_str == today_str:
                continue
            if last_used_str:
                try:
                    last_date = datetime.strptime(last_used_str, "%Y-%m-%d")
                    if last_date.year == today.year and last_date.month == today.month:
                        continue
                except:
                    continue

            is_reset_this_acc = False
            for eng in list(acc["engine_status"].keys()):
                if acc["engine_status"][eng] == "exhausted":
                    acc["engine_status"][eng] = "valid"
                    is_reset_this_acc = True
            
            if is_reset_this_acc:
                acc["last_used"] = ""
                need_save = True
                print(f"🔄 [引擎级月度自动恢复] 账号 {acc['secret_id']} 所有识别引擎重置为可用。")
                
        if need_save:
            try:
                with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(accounts, f, indent=4)
            except: pass
        return accounts
    def save_credentials(self):
        raw_text = self.txt_cred.get("1.0", tk.END).strip()
        if not raw_text:
            CustomDialog(self.window, "提示", "配置输入框内容不能为空！", "warning")
            return
            
        ids = re.findall(r'SecretId:\s*([^\s#\[\n]+)', raw_text)
        keys = re.findall(r'SecretKey:\s*([^\s#\n]+)', raw_text)
        
        if not ids or not keys or len(ids) != len(keys):
            CustomDialog(self.window, "解析失败", "文本格式解析失败，请确保成对输入 SecretId 与 SecretKey 行！", "error")
            return
            
        new_accounts = []
        old_maps = {}
        if os.path.exists(CRED_CONFIG_FILE):
            try:
                with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                    for old_a in json.load(f): old_maps[old_a["secret_id"]] = old_a
            except: pass
        for i in range(len(ids)):
            s_id = ids[i].strip()
            s_key = keys[i].strip()
            old_item = old_maps.get(s_id, {})
            
            engine_status = old_item.get("engine_status", {
                "GeneralBasicOCR": "valid",
                "GeneralAccurateOCR": "valid"
            })
            
            new_accounts.append({
                "secret_id": s_id,
                "secret_key": s_key,
                "engine_status": engine_status,
                "last_used": old_item.get("last_used", "")
            })
            
        try:
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(new_accounts, f, indent=4)
            CustomDialog(self.window, "保存成功", f"成功导入并绑定 {len(new_accounts)} 个企业接口账号（引擎审计锁已就绪）！", "info")
        except Exception as e:
            CustomDialog(self.window, "保存失败", f"保存配置文件失败: {e}", "error")

    def start_async_thread(self):
        t = threading.Thread(target=self.run_async_loop_worker)
        t.daemon = True
        t.start()

    def convert_to_hms(self, seconds):
        hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    def get_active_routing(self):
        """
        🎯 核心策略调度路由器：
        从前往后扫描账号列表，执行 (账户 -> 普通引擎 -> 高精度引擎) 双阀门依次降级切流。
        """
        if not os.path.exists(CRED_CONFIG_FILE): return None
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            accounts = self.check_and_reset_monthly(accounts)
            
            for acc in accounts:
                estatus = acc.get("engine_status", {})
                if estatus.get("GeneralBasicOCR", "valid") == "valid":
                    return acc, "GeneralBasicOCR"
                if estatus.get("GeneralAccurateOCR", "valid") == "valid":
                    return acc, "GeneralAccurateOCR"
        except: pass
        return None

    def mark_engine_exhausted(self, secret_id, action_name):
        """将特定账号的特定引擎精准标记为用尽并存盘缓存"""
        if not os.path.exists(CRED_CONFIG_FILE): return
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            for acc in accounts:
                if acc["secret_id"] == secret_id:
                    if "engine_status" not in acc:
                        acc["engine_status"] = {"GeneralBasicOCR": "valid", "GeneralAccurateOCR": "valid"}
                    acc["engine_status"][action_name] = "exhausted"
                    acc["last_used"] = datetime.now().strftime("%Y-%m-%d")
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=4)
        except: pass
    def run_async_loop_worker(self):
        global_start_time = time.time()
        
        target_dir = os.path.normpath(self.entry_path.get().strip())
        if not target_dir or not os.path.exists(target_dir):
            CustomDialog(self.window, "路径无效", "请选择有效的图片文件夹路径！", "error")
            return

        self.btn_start.config(state=tk.DISABLED, bg="#CCCCCC")
        self.label_status.config(text="⏳ 正在扫描清点本地文件夹路径...", fg="#D47A00")
        self.window.update()

        supported_exts = ('.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG')
        folder_to_images_map = {}
        all_images_flat = [] 
        for root_path, _, files in os.walk(target_dir):
            current_folder_imgs = [os.path.join(root_path, f) for f in files if f.endswith(supported_exts)]
            if current_folder_imgs:
                folder_to_images_map[root_path] = current_folder_imgs
                all_images_flat.extend(current_folder_imgs)

        total_images = len(all_images_flat)
        if total_images == 0:
            self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
            self.label_status.config(text="💡 状态: 准备就绪", fg="#333333")
            CustomDialog(self.window, "未检测到图片", "所选文件夹及子目录下未检测到任何账单图片！", "warning")
            return
        self.progress_bar["maximum"] = total_images
        self.progress_bar["value"] = 0
        self.label_status.config(text="⏳ 双安全阀流控轮询序列启动...", fg="#D47A00")
        
        raw_outputs = []
        pending_images = all_images_flat.copy()

        while pending_images and self.get_active_routing():
            route_res = self.get_active_routing()
            acc, active_engine = route_res
            s_id, s_key = acc["secret_id"], acc["secret_key"]
            
            eng_lbl = "普通识别" if active_engine == "GeneralBasicOCR" else "高精度识别"
            self.label_eta.config(text=f"正在运转: 账户 {s_id[:6]}... 🔄 引擎: {eng_lbl}", fg="#004B87")
            self.window.update()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            tasks_map = {}
            for img_path in pending_images:
                coro = core_logic.async_ocr_request(img_path, s_id, s_key, active_engine)
                tasks_map[img_path] = loop.create_task(coro)
            
            loop.run_until_complete(asyncio.gather(*tasks_map.values(), return_exceptions=True))
            loop.close()
            failed_collected_images = []
            engine_triggered_exhausted = False
            
            for img_path, task in tasks_map.items():
                exc = task.exception()
                if exc:
                    failed_collected_images.append(img_path)
                    if isinstance(exc, ValueError) and str(exc) == "ENGINE_EXHAUSTED":
                        engine_triggered_exhausted = True
                else:
                    ocr_res = task.result()
                    img_base_name, _ = os.path.splitext(os.path.basename(img_path))
                    raw_outputs.append((img_base_name, ocr_res))
                    
                    current_done_count = len(raw_outputs)
                    self.progress_bar["value"] = current_done_count
                    self.label_counter.config(text=f"已成功识别: {current_done_count} 张 / 剩余待定: {total_images - current_done_count} 张")
                    self.window.update()
            
            if engine_triggered_exhausted:
                self.mark_engine_exhausted(s_id, active_engine)
                
            pending_images = failed_collected_images
            self.progress_bar["value"] = len(raw_outputs)
            self.window.update()
            
            if pending_images and self.get_active_routing():
                time.sleep(0.5)

        ocr_result_registry = {name: ocr for name, ocr in raw_outputs if ocr}
        
        if pending_images and not self.get_active_routing():
            self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
            self.label_status.config(text="❌ 错误：所有配置账户的双引擎额度全部耗尽，对账强制终止。", fg="red")
            failed_folders = sorted(list(set(os.path.dirname(p) for p in pending_images)))
            error_message = f"所有企业 OCR 账户的【普通版】与【高精度版】均已耗尽！\n未识别图片: {len(pending_images)} 张。\n\n📍 失败文件夹列表："
            CustomDialog(self.window, "所有账户全引擎额度耗尽", error_message, "error", folder_list=failed_folders)
            return 
            
        self.save_to_excel_logic(folder_to_images_map, ocr_result_registry, global_start_time)
    def save_to_excel_logic(self, folder_to_images_map, ocr_result_registry, global_start_time):
        self.label_status.config(text="⏳ 数据回传完毕，正在执行结构化深度对账与本地 Excel 存盘...", fg="#004B87")
        self.window.update()

        columns_layout = [
            "图片名称", "采购日期", "置信度", "付款状态", "置信度", "收款官方", "置信度", "付款金额", "置信度", 
            "支付日期", "置信度", "支付时间", "置信度", "付款方式", "置信度", "交易单号", "置信度", "商户全称", 
            "置信度", "商户单号", "置信度", "系统记账日期", "采购对账单号"
        ]

        for current_folder_path, img_paths_list in folder_to_images_map.items():
            folder_matrix_rows = []
            for img_abs_path in img_paths_list:
                img_base_name, _ = os.path.splitext(os.path.basename(img_abs_path))
                ocr_list = ocr_result_registry.get(img_base_name)
                if not ocr_list: continue
                clean_row = core_logic.clean_and_parse_ocr(img_base_name, ocr_list)
                row_cells = [
                    clean_row["图片名称"], clean_row["采购日期"], clean_row["采购日期_置信度"],
                    clean_row["付款状态"], clean_row["付款状态_置信度"], clean_row["收款官方"], clean_row["收款官方_置信度"],
                    clean_row["付款金额"], clean_row["付款金额_置信度"], clean_row["支付日期"], clean_row["支付日期_置信度"],
                    clean_row["支付时间"], clean_row["支付时间_置信度"], clean_row["付款方式"], clean_row["付款方式_置信度"],
                    clean_row["交易单号"], clean_row["交易单号_置信度"], clean_row["商户全称"], clean_row["商户全称_置信度"],
                    clean_row["商户单号"], clean_row["商户单号_置信度"], clean_row["系统记账日期"], clean_row["采购对账单号"]
                ]
                folder_matrix_rows.append(row_cells)
            
            if not folder_matrix_rows: continue
            sub_folder_name = os.path.basename(current_folder_path) or "账单"
            local_output_path = os.path.join(current_folder_path, f"{sub_folder_name}批量账单.xlsx")
            
            df_local = pd.DataFrame(folder_matrix_rows, columns=columns_layout)
            valid_col_indices = []
            total_cols_count = len(df_local.columns)
            for i in range(total_cols_count):
                col_name = df_local.columns[i]
                if col_name == "置信度":
                    col_data = df_local.iloc[:, i].astype(str).str.strip()
                    if col_data.eq("").all() or col_data.eq("nan").all(): 
                        continue
                valid_col_indices.append(i)
                
            df_local = df_local.iloc[:, valid_col_indices]
            df_local.to_excel(local_output_path, index=False)

        total_full_duration = time.time() - global_start_time
        hms_duration = self.convert_to_hms(total_full_duration)

        self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
        self.label_status.config(text=f"✅ 完成！总计真实全链耗时: {hms_duration}", fg="green")
        
        target_dir = os.path.normpath(self.entry_path.get().strip())
        sub_folder_name = os.path.basename(target_dir) or "账单"
        excel_name = f"{sub_folder_name}批量账单.xlsx"

        def on_open_folder():
            try:
                if os.path.exists(target_dir): os.startfile(target_dir)
            except Exception as e: CustomDialog(self.window, "打开失败", f"无法打开文件夹: {e}", "error")

        msg_text = f"对账结果已成功保存并生成在当前图片文件夹：\n👉 {excel_name}\n⏱️ 总计真实全链耗时：{hms_duration}"
        CustomDialog(self.window, "🎉 对账任务完成", msg_text, "info", callback_action=on_open_folder, btn_action_text="📂 打开文件夹")

if __name__ == "__main__":
    root = tk.Tk()
    app = BillOcrGui(root)
    root.mainloop()
