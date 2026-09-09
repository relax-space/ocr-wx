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

APP_SETTINGS_FILE = os.path.join(BASE_DIR, '.ocr_app_settings.json')
CRED_CONFIG_FILE = os.path.join(BASE_DIR, '.ocr_credentials_secret.json')
class CustomDialog(tk.Toplevel):
    """
    ⚡ 全自定义高颜值 Tkinter 弹窗（紧凑空间版）
    """
    def __init__(self, parent, title, message, mode="info", callback_action=None, btn_action_text=" 确 定 ", folder_list=None):
        super().__init__(parent)
        self.attributes("-alpha", 0.0) 
        self.title(title)
        self.configure(bg="#F3F3F3")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        theme_color = "#0078D4" if mode == "info" else "#D47A00" if mode == "warning" else "#E81123"
        
        # 窗口总高度缩回最舒适紧凑的 360，绝不无形长高
        dialog_width, dialog_height = 480, 260 if not folder_list else 360
        
        main_w = parent.winfo_width()
        main_h = parent.winfo_height()
        main_x = parent.winfo_x()
        main_y = parent.winfo_y()
        pos_x = main_x + (main_w - dialog_width) // 2
        pos_y = main_y + (main_h - dialog_height) // 2
        self.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        # 先用 side="bottom" 强行把动作大按钮焊死在底层，拒绝任何物理被顶掉 Bug
        btn_frame = tk.Frame(self, pady=10, bg="#F3F3F3")
        btn_frame.pack(fill="x", side="bottom")

        if callback_action:
            btn_action = tk.Button(btn_frame, text=btn_action_text, font=("微软雅黑", 10, "bold"), bg="#107C41", fg="white", padx=15, pady=3, command=lambda: [callback_action(), self.destroy()])
            btn_action.pack(side="right", padx=(10, 25))
            btn_cancel = tk.Button(btn_frame, text=" 取 消 ", font=("微软雅黑", 10), bg="#E1E1E1", fg="#333333", padx=15, pady=3, command=self.destroy)
            btn_cancel.pack(side="right")
        else:
            btn_close = tk.Button(btn_frame, text=" 关 闭 ", font=("微软雅黑", 10), bg=theme_color, fg="white", padx=20, pady=3, command=self.destroy)
            btn_close.pack(side="right", padx=25)
        # 再渲染中部的文本和列表内容
        main_frame = tk.Frame(self, bg="#F3F3F3", padx=25, pady=10)
        main_frame.pack(fill="both", expand=True)

        lbl_title = tk.Label(main_frame, text=title, font=("微软雅黑", 12, "bold"), fg=theme_color, bg="#F3F3F3")
        lbl_title.pack(anchor="w", pady=(0, 4))

        lbl_msg = tk.Label(main_frame, text=message, font=("微软雅黑", 10), justify="left", fg="#333333", bg="#F3F3F3", wraplength=430)
        lbl_msg.pack(anchor="w", pady=(2, 4))
        # 将 height 限制死为 4 行。多于 4 行时在内部优雅刷出滚动条，不挤压一丁点外部空间！
        if folder_list:
            list_frame = tk.Frame(main_frame, bg="#F3F3F3")
            list_frame.pack(fill="both", expand=True, pady=(2, 2))
            scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            box = tk.Listbox(list_frame, font=("微软雅黑", 9), fg="#555555", bg="white", yscrollcommand=scrollbar.set, highlightthickness=1, highlightcolor="#CCCCCC", height=4)
            box.pack(side=tk.LEFT, fill="both", expand=True)
            scrollbar.config(command=box.yview)
            for f_path in folder_list:
                box.insert(tk.END, f" 📄 {f_path}")
        
        # 🚀 解除透明锁完全现身
        self.attributes("-alpha", 1.0)
        self.attributes("-topmost", True)
class BillOcrGui:
    def __init__(self, window):
        self.window = window
        self.window.title("⚡ 微信支付图片多账号多引擎智能轮询对账系统 v2.2")
        self.window.geometry("640x560")  # 开机默认折叠形态高度
        self.window.resizable(False, False)
        
        frame_cred = tk.LabelFrame(window, text=" 🔐 企业微信 OCR 凭证批量配置 ", font=("微软雅黑", 9, "bold"), padx=10, pady=6)
        frame_cred.pack(fill="x", padx=25, pady=4)
        
        self.txt_cred = tk.Text(frame_cred, height=5, width=65, font=("Consolas", 9))
        self.txt_cred.pack(pady=5, side=tk.LEFT, fill="x", expand=True)
        
        btn_save_cred = tk.Button(frame_cred, text="💾 保存\n配置", command=self.save_credentials, bg="#107C41", fg="white", font=("微软雅黑", 10, "bold"), width=6)
        btn_save_cred.pack(side=tk.RIGHT, padx=5, fill="y", pady=5)
        frame_dir = tk.Frame(window, pady=6)
        frame_dir.pack(fill="x", padx=25)
        tk.Label(frame_dir, text="图片文件夹:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.entry_path = tk.Entry(frame_dir, width=42, font=("微软雅黑", 10))
        self.entry_path.pack(side=tk.LEFT, padx=10)
        tk.Button(frame_dir, text=" 浏览... ", command=self.select_folder, bg="#E1E1E1").pack(side=tk.LEFT)

        # 高级隐藏抽屉的状态控制锁
        self.adv_panel_expanded = False
        
        # ⚙️ 齿轮高级控制文字纽扣
        self.btn_toggle_adv = tk.Label(window, text="⚙️ 财务高级业务控制策略 (点击展开) 🔽", font=("微软雅黑", 9, "bold"), fg="#004B87", cursor="hand2")
        self.btn_toggle_adv.pack(anchor="w", padx=25, pady=(4, 2))
        self.btn_toggle_adv.bind("<Button-1>", lambda e: self.toggle_advanced_panel())

        # 预加载父LabelFrame，开机时不 pack
        self.frame_adv = tk.LabelFrame(window, text=" 🛠️ 财务高级业务控制策略（企业深度调优） ", font=("微软雅黑", 9, "bold"), fg="#004B87", padx=15, pady=8)
        strategy_frame = tk.Frame(self.frame_adv)
        strategy_frame.pack(fill="x", pady=4)
        tk.Label(strategy_frame, text="识别策略权重:", font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT)
        self.combo_mode = ttk.Combobox(strategy_frame, values=["普通优先（最快且省额度）", "高精度优先（识别更精准）"], width=24, state="readonly")
        self.combo_mode.pack(side=tk.LEFT, padx=10)
        self.combo_mode.set("普通优先（最快且省额度）")
        
        lbl_hint_prio = tk.Label(self.frame_adv, text="💡 提示：[普通优先] 会先耗尽所有账号的普通额度再切至高精度；[高精度优先] 则直接强制调度高级引擎。", font=("微软雅黑", 8), fg="#666666", justify="left")
        lbl_hint_prio.pack(anchor="w", pady=(0, 6))
        thresh_frame = tk.Frame(self.frame_adv)
        thresh_frame.pack(fill="x", pady=4)
        tk.Label(thresh_frame, text="高精度归一阈值:", font=("微软雅黑", 9, "bold")).pack(side=tk.LEFT)
        self.entry_thresh = tk.Entry(thresh_frame, width=8, font=("Consolas", 10, "bold"), fg="#107C41")
        self.entry_thresh.pack(side=tk.LEFT, padx=10)
        self.entry_thresh.insert(0, "0.99")
        tk.Label(thresh_frame, text="(有效范围: 0.00 ~ 1.00)", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)
        
        lbl_hint_th = tk.Label(self.frame_adv, text="💡 说明：分数达到设定值会自动变为 1.00，表示绝对信任，方便财务直接对账。推荐选择 0.99。", font=("微软雅黑", 8), fg="#D47A00", wraplength=540, justify="left")
        lbl_hint_th.pack(anchor="w", pady=(0, 2))
        self.frame_progress = tk.LabelFrame(window, text=" 📊 实时多账户多引擎轮询流控进度 ", font=("微软雅黑", 9, "bold"), padx=15, pady=6)
        self.frame_progress.pack(fill="x", padx=25, pady=4)
        
        self.label_counter = tk.Label(self.frame_progress, text="等待启动...", font=("微软雅黑", 10))
        self.label_counter.pack(anchor="w")
        self.label_eta = tk.Label(self.frame_progress, text="正在运转的引擎: --", font=("微软雅黑", 10), fg="#004B87")
        self.label_eta.pack(anchor="w", pady=(2, 4))
        
        self.progress_bar = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=2)
        self.label_status = tk.Label(window, text="💡 状态: 准备就绪。双层全级联控制策略已绑定！", font=("微软雅黑", 10), fg="#333333", pady=3)
        self.label_status.pack()

        self.btn_start = tk.Button(window, text="🚀 启动云端高并发对账", command=self.start_async_thread, font=("微软雅黑", 12, "bold"), bg="#0078D4", fg="white", width=25, height=2)
        self.btn_start.pack(pady=4)

        frame_disclaimer = tk.LabelFrame(window, text=" ⚖️ 法律与合规免责声明 ", font=("微软雅黑", 9, "bold"), fg="#D47A00", padx=10, pady=4)
        frame_disclaimer.pack(fill="x", padx=25, pady=4)
        disclaimer_text = "提示:本工具仅限专机内部效率比对使用。多账号轮询需确保各个账号均已获取合法凭证。因明文外传导致的信息泄露风险由操作方承担，开发者不对财务账目真实性及审计合规结果承担任何法律责任。"
        lbl_disc = tk.Label(frame_disclaimer, text=disclaimer_text, font=("微软雅黑", 8), fg="#666666", wraplength=550, justify="left")
        lbl_disc.pack()

        self.load_history_config()
    def toggle_advanced_panel(self):
        """高级扩展面板动态平滑抽屉式伸缩控制"""
        if self.adv_panel_expanded:
            self.frame_adv.pack_forget() 
            self.btn_toggle_adv.config(text="⚙️ 财务高级业务控制策略 (点击展开) 🔽")
            self.window.geometry("640x560")
            self.adv_panel_expanded = False
        else:
            self.frame_adv.pack(fill="x", padx=25, pady=6, after=self.btn_toggle_adv)
            self.btn_toggle_adv.config(text="⚙️ 财务高级业务控制策略 (点击收起) 🔼")
            self.window.geometry("640x740")
            self.adv_panel_expanded = True

    def select_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            clean_dir = os.path.normpath(folder_selected)
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, clean_dir)
            self.save_app_settings()
    def save_app_settings(self):
        cfg = {"path": self.entry_path.get().strip(), "mode": self.combo_mode.get(), "threshold": self.entry_thresh.get().strip()}
        try:
            with open(APP_SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=4, ensure_ascii=False)
        except: pass
    def load_history_config(self):
        if os.path.exists(APP_SETTINGS_FILE):
            try:
                with open(APP_SETTINGS_FILE, "r", encoding="utf-8") as f: cfg = json.load(f)
                if os.path.exists(cfg.get("path", "")): 
                    self.entry_path.delete(0, tk.END)
                    self.entry_path.insert(0, cfg["path"])
                if "mode" in cfg: self.combo_mode.set(cfg["mode"])
                if "threshold" in cfg:
                    self.entry_thresh.delete(0, tk.END)
                    self.entry_thresh.insert(0, cfg["threshold"])
            except: pass
        if os.path.exists(CRED_CONFIG_FILE):
            try:
                with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f: accounts = json.load(f)
                accounts = self.check_and_reset_monthly(accounts)
                text_show = ""
                for idx, acc in enumerate(accounts):
                    engine_states = acc.get("engine_status", {})
                    saved_name = acc.get("account_name", "").strip()
                    if not saved_name or saved_name == "未知账号":
                        saved_name = f"账号{idx + 1}"
                    
                    acc_label = f"# {saved_name}"
                    b_status = " [普通版用尽]" if engine_states.get("GeneralBasicOCR") == "exhausted" else ""
                    a_status = " [高精度用尽]" if engine_states.get("GeneralAccurateOCR") == "exhausted" else ""
                    text_show += f"{acc_label}{b_status}{a_status}\nSecretId:{acc['secret_id']}\nSecretKey:{acc['secret_key']}\n\n"
                self.txt_cred.delete("1.0", tk.END)
                self.txt_cred.insert("1.0", text_show.strip())
                
                routing_res = self.get_active_routing()
                if routing_res:
                    active_acc, _ = routing_res
                    ready_name = active_acc.get("account_name", "账号1")
                    self.label_eta.config(text=f"当前预备就绪账号: {ready_name}", fg="#107C41")
                else:
                    self.label_eta.config(text=f"❌ 警告：未检测到任何可用账号或额度已全部耗尽！", fg="red")
            except: pass
    def check_and_reset_monthly(self, accounts):
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        need_save = False
        for acc in accounts:
            if "engine_status" not in acc:
                acc["engine_status"] = {"GeneralBasicOCR": "valid", "GeneralAccurateOCR": "valid"}
                need_save = True
            last_used_str = acc.get("last_used", "").strip()
            if last_used_str == today_str: continue
            if last_used_str:
                try:
                    last_date = datetime.strptime(last_used_str, "%Y-%m-%d")
                    if last_date.year == today.year and last_date.month == today.month: continue
                except: continue
            is_reset_this_acc = False
            for eng in list(acc["engine_status"].keys()):
                if acc["engine_status"][eng] == "exhausted":
                    acc["engine_status"][eng] = "valid"
                    is_reset_this_acc = True
            if is_reset_this_acc:
                acc["last_used"] = ""
                need_save = True
        if need_save:
            try:
                with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(accounts, f, indent=4)
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
            CustomDialog(self.window, "解析失败", "文本格式解析失败！", "error")
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
            new_accounts.append({
                "account_name": f"账号{i+1}",
                "secret_id": s_id, "secret_key": s_key,
                "engine_status": old_item.get("engine_status", {"GeneralBasicOCR": "valid", "GeneralAccurateOCR": "valid"}),
                "last_used": old_item.get("last_used", "")
            })
        try:
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(new_accounts, f, indent=4)
            CustomDialog(self.window, "保存成功", f"成功导入并绑定 {len(new_accounts)} 个企业接口账号！", "info")
            self.txt_cred.delete("1.0", tk.END)
            self.load_history_config()
        except Exception as e: CustomDialog(self.window, "保存失败", f"保存配置文件失败: {e}", "error")
    def get_active_routing(self):
        if not os.path.exists(CRED_CONFIG_FILE): return None
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f: accounts = json.load(f)
            accounts = self.check_and_reset_monthly(accounts)
            is_accurate_first = "高精度优先" in self.combo_mode.get()
            
            for idx, acc in enumerate(accounts):
                estatus = acc.get("engine_status", {})
                if "account_name" not in acc: acc["account_name"] = f"账号{idx + 1}"
                
                if is_accurate_first:
                    if estatus.get("GeneralAccurateOCR", "valid") == "valid": return acc, "GeneralAccurateOCR"
                    if estatus.get("GeneralBasicOCR", "valid") == "valid": return acc, "GeneralBasicOCR"
                else:
                    if estatus.get("GeneralBasicOCR", "valid") == "valid": return acc, "GeneralBasicOCR"
                    if estatus.get("GeneralAccurateOCR", "valid") == "valid": return acc, "GeneralAccurateOCR"
        except: pass
        return None

    def mark_engine_exhausted(self, secret_id, action_name):
        if not os.path.exists(CRED_CONFIG_FILE): return
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f: accounts = json.load(f)
            for acc in accounts:
                if acc["secret_id"] == secret_id:
                    acc["engine_status"][action_name] = "exhausted"
                    acc["last_used"] = datetime.now().strftime("%Y-%m-%d")
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(accounts, f, indent=4)
        except: pass

    def start_async_thread(self):
        try:
            val = float(self.entry_thresh.get().strip())
            if not (0.0 <= val <= 1.0): raise ValueError
        except:
            CustomDialog(self.window, "参数无效", "高置信度归一阈值必须在 0.0 到 1.0 之间！", "error")
            return
        self.save_app_settings()
        t = threading.Thread(target=self.run_async_loop_worker)
        t.daemon = True
        t.start()

    def convert_to_hms(self, seconds):
        return f"{int(seconds // 3600):02d}:{int((seconds % 3600) // 60):02d}:{int(seconds % 60):02d}"
    def run_async_loop_worker(self):
        global_start_time = time.time()
        target_dir = os.path.normpath(self.entry_path.get().strip())
        if not target_dir or not os.path.exists(target_dir):
            CustomDialog(self.window, "路径无效", "请选择有效的图片文件夹路径！", "error")
            return
        self.btn_start.config(state=tk.DISABLED, bg="#CCCCCC")
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
            CustomDialog(self.window, "未检测到图片", "未检测到任何账单图片！", "warning")
            return
            
        self.progress_bar["maximum"] = total_images
        self.progress_bar["value"] = 0
        raw_outputs = []
        pending_images = all_images_flat.copy()
        network_or_damaged_images = []

        last_account_id = None
        if not hasattr(self, 'dialog_is_showing'): self.dialog_is_showing = False

        while pending_images and self.get_active_routing():
            acc, active_engine = self.get_active_routing()
            s_id, s_key = acc["secret_id"], acc["secret_key"]
            current_acc_name = acc.get("account_name", "账号1")
            
            if last_account_id is not None and last_account_id != s_id:
                self.label_eta.config(text=f"⚠️ 正在切换到{current_acc_name}... 请稍候", fg="#D47A00")
                self.window.update()
                
            last_account_id = s_id
            mode_lbl = "高精度" if active_engine == "GeneralAccurateOCR" else "普通版"
            self.label_eta.config(text=f"正在运转: {current_acc_name} 模式: {mode_lbl}", fg="#004B87")
            self.window.update()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            tasks_map = {p: loop.create_task(core_logic.async_ocr_request(p, s_id, s_key, active_engine)) for p in pending_images}
            loop.run_until_complete(asyncio.gather(*tasks_map.values(), return_exceptions=True))
            loop.close()
            
            failed_collected_images = []
            engine_triggered_exhausted = False
            
            for img_path, task in tasks_map.items():
                exc = task.exception()
                if exc:
                    failed_collected_images.append(img_path)
                    if isinstance(exc, ValueError) and str(exc) == "ENGINE_EXHAUSTED": engine_triggered_exhausted = True
                else:
                    raw_outputs.append((img_path, task.result()))
                    self.progress_bar["value"] = len(raw_outputs)
                    self.label_counter.config(text=f"已成功识别: {len(raw_outputs)} 张 / 剩余待定: {total_images - len(raw_outputs)} 张")
                    self.window.update()
                    
            if engine_triggered_exhausted: 
                self.mark_engine_exhausted(s_id, active_engine)
                self.window.after(0, lambda: [self.txt_cred.delete("1.0", tk.END), self.load_history_config()])
            
            if len(failed_collected_images) == len(pending_images) and not engine_triggered_exhausted:
                print(f"⚠️ [提示] 发现 {len(failed_collected_images)} 张图片因网络波动或文件损坏无法解析，系统已自动登记错题本并平滑跳过...")
                for bad_img in failed_collected_images: network_or_damaged_images.append(os.path.basename(bad_img))
                failed_collected_images = []
                
            pending_images = failed_collected_images

        ocr_result_registry = {str(name): ocr for name, ocr in raw_outputs if ocr}
        if network_or_damaged_images:
            try:
                txt_path = os.path.join(target_dir, "网络错误或图片损坏核对说明.txt")
                with open(txt_path, "w", encoding="utf-8") as log_f:
                    log_f.write(f"自动对账系统自检报告（生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}）\n")
                    log_f.write(f"-" * 70 + "\n财务温馨提示：\n以下图片在传输时遇到了【网络抖动超时】或【图片本身损坏/格式不兼容】。\n为了不耽误其余账单的高速对账，系统已跳过它们。请财务老师手动核对：\n" + "-" * 70 + "\n\n")
                    for name in network_or_damaged_images: log_f.write(f" 📄 [需人工核对] -> {name}\n")
            except: pass

        if pending_images and not self.get_active_routing():
            self.window.after(0, lambda: [self.txt_cred.delete("1.0", tk.END), self.load_history_config()])
            self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
            if not self.dialog_is_showing:
                self.dialog_is_showing = True
                def reset_lock_callback(): self.dialog_is_showing = False
                CustomDialog(self.window, "额度全部耗尽", f"全引擎额度均已耗尽！", "error", callback_action=reset_lock_callback, folder_list=sorted(list(set(os.path.dirname(p) for p in pending_images))))
            return 
        self.save_to_excel_logic(folder_to_images_map, ocr_result_registry, global_start_time, network_or_damaged_images)

    def save_to_excel_logic(self, folder_to_images_map, ocr_result_registry, global_start_time, network_or_damaged_images=None):
        self.label_status.config(text="⏳ 正在执行结构化深度对账与本地 Excel 存盘...", fg="#004B87")
        self.window.update()
        try: user_threshold = float(self.entry_thresh.get().strip())
        except: user_threshold = 0.99

        columns_layout = [
            "图片名称", "采购日期", "置信度", "付款状态", "置信度", "收款官方", "置信度", "付款金额", "置信度", 
            "支付日期", "置信度", "支付时间", "置信度", "付款方式", "置信度", "交易单号", "置信度", "商户全称", 
            "置信度", "商户单号", "置信度", "系统记账日期", "采购对账单号"
        ]

        for current_folder_path, img_paths_list in folder_to_images_map.items():
            folder_matrix_rows = []
            for img_abs_path in img_paths_list:
                img_base_name, _ = os.path.splitext(os.path.basename(img_abs_path))
                ocr_list = ocr_result_registry.get(str(img_abs_path))
                if not ocr_list: continue
                clean_row = core_logic.clean_and_parse_ocr(img_base_name, ocr_list, conf_threshold=user_threshold)
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
            valid_col_indices = [i for i in range(len(df_local.columns)) if df_local.columns[i] != "置信度" or not (df_local.iloc[:, i].astype(str).str.strip().eq("").all() or df_local.iloc[:, i].astype(str).str.strip().eq("nan").all())]
            df_local.iloc[:, valid_col_indices].to_excel(local_output_path, index=False)

        hms_duration = self.convert_to_hms(time.time() - global_start_time)
        self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
        target_dir = os.path.normpath(self.entry_path.get().strip())
        excel_name = f"{os.path.basename(target_dir) or '账单'}批量账单.xlsx"
        
        if network_or_damaged_images:
            self.label_status.config(text=f"⚠️ 对账完毕，但发现有 {len(network_or_damaged_images)} 张异常账单需人工核对", fg="#D47A00")
            warn_msg = f"对账结果已成功导出生成！\n👉 {excel_name}\n⏱️ 总耗时：{hms_duration}\n\n🚨 警告：以下 {len(network_or_damaged_images)} 张图片在传输时遇到了【网络抖动超时】或【图片本身损坏】。请在下方列表中手动重新核对："
            CustomDialog(self.window, "⚠️ 发现异常账单需人工核对", warn_msg, "warning", callback_action=lambda: os.startfile(target_dir) if os.path.exists(target_dir) else None, btn_action_text="📂 打开文件夹并核对", folder_list=network_or_damaged_images)
        else:
            self.label_status.config(text=f"✅ 完成！总记全链耗时: {hms_duration}", fg="green")
            succ_msg = f"对账结果已成功保存并生成在当前图片文件夹：\n👉 {excel_name}\n⏱️ 总计真实全链耗时：{hms_duration}"
            CustomDialog(self.window, "🎉 对账任务完成", succ_msg, "info", callback_action=lambda: os.startfile(target_dir) if os.path.exists(target_dir) else None, btn_action_text="📂 打开文件夹")

if __name__ == "__main__":
    root = tk.Tk()
    app = BillOcrGui(root)
    root.mainloop()
