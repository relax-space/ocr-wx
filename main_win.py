import os
import sys
import time
import json
import threading
import asyncio
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
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
class BillOcrGui:
    def __init__(self, window):
        self.window = window
        self.window.title("⚡ 微信支付图片多账号智能轮询云对账系统 v2.0")
        self.window.geometry("640x630")
        self.window.resizable(False, False)
        
        # 1. 🔑 密钥配置面板 (支持直接复制多组)
        frame_cred = tk.LabelFrame(window, text=" 🔐 企业微信 OCR 凭证批量配置 ", font=("微软雅黑", 9, "bold"), padx=10, pady=8)
        frame_cred.pack(fill="x", padx=25, pady=8)
        
        lbl_tip = tk.Label(frame_cred, text="格式: SecretId:xxx 换行 SecretKey:sss (支持直接复制多组)", font=("微软雅黑", 8), fg="gray")
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
        self.frame_progress = tk.LabelFrame(window, text=" 📊 实时多账号轮询并发进度 ", font=("微软雅黑", 9, "bold"), padx=15, pady=8)
        self.frame_progress.pack(fill="x", padx=25, pady=5)
        
        self.label_counter = tk.Label(self.frame_progress, text="等待启动...", font=("微软雅黑", 10))
        self.label_counter.pack(anchor="w")
        self.label_eta = tk.Label(self.frame_progress, text="预估剩余时间: --", font=("微软雅黑", 10), fg="#004B87")
        self.label_eta.pack(anchor="w", pady=(2, 5))
        
        self.progress_bar = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x")

        self.label_status = tk.Label(window, text="💡 状态: 准备就绪，首次使用请批量配置密钥。", font=("微软雅黑", 10), fg="#333333", pady=3)
        self.label_status.pack()

        # 4. 🚀 启动大按钮与合规免责声明
        self.btn_start = tk.Button(window, text="🚀 启动云端高并发对账", command=self.start_async_thread, font=("微软雅黑", 12, "bold"), bg="#0078D4", fg="white", width=25, height=2)
        self.btn_start.pack(pady=5)

        frame_disclaimer = tk.LabelFrame(window, text=" ⚖️ 法律与合规免责声明 ", font=("微软雅黑", 9, "bold"), fg="#D47A00", padx=10, pady=5)
        frame_disclaimer.pack(fill="x", padx=25, pady=5)
        disclaimer_text = "提示：本工具仅限专机内部效率比对使用。多账号轮询需确保各个账号均已获取合法凭证。因明文外传导致的信息泄露风险由操作方承担，开发者不对财务账目真实性及审计合规结果承担任何法律责任。"
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
                # 检查并触发跨月自动重置次数
                accounts = self.check_and_reset_monthly(accounts)
                
                text_show = ""
                for acc in accounts:
                    status_str = "" if acc.get("status", "valid") == "valid" else " [已用尽]"
                    text_show += f"SecretId:{acc['secret_id']}{status_str}\nSecretKey:{acc['secret_key']}\n\n"
                self.txt_cred.insert("1.0", text_show.strip())
            except: pass
    def check_and_reset_monthly(self, accounts):
        """跨月重置大脑：判断是否跨月或处于1号，恢复所有可用次数"""
        today = datetime.now()
        is_first_day = (today.day == 1)
        need_save = False
        
        for acc in accounts:
            last_used_str = acc.get("last_used", "")
            need_reset = False
            
            if is_first_day:
                if last_used_str:
                    try:
                        last_date = datetime.strptime(last_used_str, "%Y-%m-%d")
                        if last_date.day != 1 or last_date.month != today.month or last_date.year != today.year:
                            need_reset = True
                    except:
                        need_reset = True
                else:
                    need_reset = True
            else:
                if last_used_str:
                    try:
                        last_date = datetime.strptime(last_used_str, "%Y-%m-%d")
                        if last_date.month != today.month or last_date.year != today.year:
                            need_reset = True
                    except:
                        need_reset = True

            if need_reset and acc.get("status") == "exhausted":
                acc["status"] = "valid"
                need_save = True
                
        if need_save:
            try:
                with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(accounts, f, indent=4)
            except: pass
        return accounts
    def save_credentials(self):
        raw_text = self.txt_cred.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("提示", "配置框不能为空！")
            return
            
        ids = re.findall(r'SecretId:\s*([^\s#\[\n]+)', raw_text)
        keys = re.findall(r'SecretKey:\s*([^\s#\n]+)', raw_text)
        
        if not ids or not keys or len(ids) != len(keys):
            messagebox.showerror("错误", "文本解析失败，请确保成对输入 SecretId 与 SecretKey 行！")
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
                "secret_id": s_id,
                "secret_key": s_key,
                "status": old_item.get("status", "valid"),
                "last_used": old_item.get("last_used", "")
            })
            
        try:
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(new_accounts, f, indent=4)
            messagebox.showinfo("成功", f"成功导入并保存 {len(new_accounts)} 个企业接口账号！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")
    def start_async_thread(self):
        t = threading.Thread(target=self.run_async_loop_worker)
        t.daemon = True
        t.start()

    def convert_to_hms(self, seconds):
        hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def get_active_account(self):
        """精准提取当前未消耗完的主密钥账号"""
        if not os.path.exists(CRED_CONFIG_FILE): return None
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            accounts = self.check_and_reset_monthly(accounts)
            for acc in accounts:
                if acc.get("status", "valid") == "valid":
                    return acc
        except: pass
        return None
    def mark_account_exhausted(self, secret_id):
        """独立、串行写入，避免任何并发脏数据污染"""
        if not os.path.exists(CRED_CONFIG_FILE): return
        try:
            with open(CRED_CONFIG_FILE, "r", encoding="utf-8") as f:
                accounts = json.load(f)
            for acc in accounts:
                if acc["secret_id"] == secret_id:
                    acc["status"] = "exhausted"
                    acc["last_used"] = datetime.now().strftime("%Y-%m-%d")
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=4)
        except: pass

    def run_async_loop_worker(self):
        target_dir = os.path.normpath(self.entry_path.get().strip())
        if not target_dir or not os.path.exists(target_dir):
            messagebox.showerror("错误", "文件夹路径无效！")
            return

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
            messagebox.showwarning("提示", "未检测到任何账单图片！")
            return
        self.btn_start.config(state=tk.DISABLED, bg="#CCCCCC")
        self.progress_bar["maximum"] = total_images
        self.progress_bar["value"] = 0
        self.label_status.config(text="⏳ 动态序列轮询并发流控启动...", fg="#D47A00")
        
        start_recognition_time = time.time()
        raw_outputs = []
        pending_images = all_images_flat.copy()

        # 🚀 外部主大循环：只要还有未成功图片且存在健康账号，就一轮轮清洗
        while pending_images and self.get_active_account():
            acc = self.get_active_account()
            s_id, s_key = acc["secret_id"], acc["secret_key"]
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 1. 动态克隆映射当前轮次的异步并发流
            tasks_map = {}
            for img_path in pending_images:
                coro = core_logic.async_ocr_request(img_path, s_id, s_key)
                tasks_map[img_path] = loop.create_task(coro)
            
            # 2. 并发安全等待当前账号名下的所有任务完整执行完毕，绝不中途退出
            loop.run_until_complete(asyncio.gather(*tasks_map.values(), return_exceptions=True))
            loop.close()
            
            # 3. 在并发彻底终结后，有秩序地通过统一清点搜集所有不成功的图片参数
            failed_collected_images = []
            account_triggered_exhausted = False
            
            for img_path, task in tasks_map.items():
                exc = task.exception()
                if exc:
                    failed_collected_images.append(img_path)
                    # 判定是不是额度用光的信号
                    if isinstance(exc, ValueError) and str(exc) == "ACCOUNT_EXHAUSTED":
                        account_triggered_exhausted = True
                else:
                    # 识别圆满成功
                    ocr_res = task.result()
                    img_base_name, _ = os.path.splitext(os.path.basename(img_path))
                    raw_outputs.append((img_base_name, ocr_res))
            
            # 4. 彻底脱离并发，同步进行账号状态写入，仅修改发生错误的当前账号
            if account_triggered_exhausted:
                self.mark_account_exhausted(s_id)
                
            # 5. 更新下一轮需要重试的队列
            pending_images = failed_collected_images
            
            # 更新主界面大进度条
            self.progress_bar["value"] = len(raw_outputs)
            self.label_counter.config(text=f"已成功处理: {len(raw_outputs)} 张 / 剩余待定: {len(pending_images)} 张")
            self.window.update()
            
            if pending_images and self.get_active_account():
                time.sleep(0.5)  # 换号时留出无感存盘与套接字冷却微秒

        hms_duration = self.convert_to_hms(time.time() - start_recognition_time)
        ocr_result_registry = {name: ocr for name, ocr in raw_outputs if ocr}
        
        # 6. 唯有所有配置的账号都耗尽且 pend_images 不为空，才触发终极弹窗
        if pending_images and not self.get_active_account():
            self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
            self.label_status.config(text="❌ 错误：因所有账号额度耗尽，对账任务被迫中断。", fg="red")
            messagebox.showerror("额度耗尽", f"所有配置的账号次数均已耗尽！\n未识别图片共计 {len(pending_images)} 张。\n请补充密钥或等待下月1号自动恢复。")
            return 
            
        self.save_to_excel_logic(folder_to_images_map, ocr_result_registry, hms_duration)
    def save_to_excel_logic(self, folder_to_images_map, ocr_result_registry, hms_duration):
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

        self.btn_start.config(state=tk.NORMAL, bg="#0078D4")
        self.label_status.config(text=f"✅ 完成！耗时: {hms_duration}", fg="green")
        
        target_dir = os.path.normpath(self.entry_path.get().strip())
        sub_folder_name = os.path.basename(target_dir) or "账单"
        excel_name = f"{sub_folder_name}批量账单.xlsx"

        dialog = tk.Toplevel(self.window)
        dialog.title("🎉 对账任务完成")
        dialog.configure(bg="#F3F3F3")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()

        dialog_width, dialog_height = 420, 200
        self.window.update_idletasks()
        main_w, main_h = self.window.winfo_width(), self.window.winfo_height()
        main_x, main_y = self.window.winfo_x(), self.window.winfo_y()
        pos_x = main_x + (main_w - dialog_width) // 2
        pos_y = main_y + (main_h - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")

        main_frame = tk.Frame(dialog, bg="#F3F3F3", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        tk.Label(main_frame, text="⚡ 云端对账全部结束！", font=("微软雅黑", 11, "bold"), fg="#0078D4", bg="#F3F3F3").grid(row=0, column=1, sticky="w")

        msg_text = f"对账结果已成功保存并生成在当前图片文件夹：\n👉 {excel_name}\n⏱️ 总计耗时：{hms_duration}"
        tk.Label(main_frame, text=msg_text, font=("微软雅黑", 10), justify="left", fg="#333333", bg="#F3F3F3").grid(row=1, column=1, sticky="w", pady=(8, 0))
        
        btn_frame = tk.Frame(dialog, pady=15, bg="#F3F3F3")
        btn_frame.pack(fill="x", side="bottom")

        def on_open_folder(path):
            try:
                if os.path.exists(path): os.startfile(path)
            except Exception as e: messagebox.showerror("错误", f"无法打开文件夹: {e}")

        btn_open = tk.Button(btn_frame, text="📂 打开文件夹", font=("微软雅黑", 10, "bold"), bg="#107C41", fg="white", padx=15, pady=3,
                             command=lambda: [on_open_folder(target_dir), dialog.destroy()])
        btn_open.pack(side="right", padx=(10, 20))
        btn_cancel = tk.Button(btn_frame, text=" 关 闭 ", font=("微软雅黑", 10), bg="#E1E1E1", fg="#333333", padx=15, pady=3, command=dialog.destroy)
        btn_cancel.pack(side="right")

if __name__ == "__main__":
    root = tk.Tk()
    app = BillOcrGui(root)
    root.mainloop()
