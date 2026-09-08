import os
import sys
import time
import json
import threading
import asyncio
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pandas as pd

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
        self.window.title("⚡ 微信支付图片异步云对账系统 v2.0 (专机专用版)")
        self.window.geometry("640x580")
        self.window.resizable(False, False)
        
        # 1. 🔑 密钥配置面板 (SecretKey带*掩码输入防窥)
        frame_cred = tk.LabelFrame(window, text=" 🔐 企业微信 OCR 凭证配置 ", font=("微软雅黑", 9, "bold"), padx=10, pady=8)
        frame_cred.pack(fill="x", padx=25, pady=10)
        
        tk.Label(frame_cred, text="SecretId:", font=("微软雅黑", 9)).grid(row=0, column=0, sticky="w", pady=3)
        self.entry_id = tk.Entry(frame_cred, width=50, font=("Consolas", 9))
        self.entry_id.grid(row=0, column=1, padx=10, sticky="w")
        
        tk.Label(frame_cred, text="SecretKey:", font=("微软雅黑", 9)).grid(row=1, column=0, sticky="w", pady=3)
        self.entry_key = tk.Entry(frame_cred, width=50, font=("Consolas", 9), show="*")
        self.entry_key.grid(row=1, column=1, padx=10, sticky="w")
        
        btn_save_cred = tk.Button(frame_cred, text="💾 保存配置", command=self.save_credentials, bg="#107C41", fg="white", font=("微软雅黑", 9))
        btn_save_cred.grid(row=0, column=2, rowspan=2, padx=5, sticky="ns")

        # 2. 文件夹路径选择面板 (已完全抹除多核下拉框)
        frame_dir = tk.Frame(window, pady=10)
        frame_dir.pack(fill="x", padx=25)
        tk.Label(frame_dir, text="图片文件夹:", font=("微软雅黑", 10)).pack(side=tk.LEFT)
        self.entry_path = tk.Entry(frame_dir, width=42, font=("微软雅黑", 10))
        self.entry_path.pack(side=tk.LEFT, padx=10)
        tk.Button(frame_dir, text=" 浏览... ", command=self.select_folder, bg="#E1E1E1").pack(side=tk.LEFT)

        # 3. 📊 实时高并发执行进度面板
        self.frame_progress = tk.LabelFrame(window, text=" 📊 实时高并发执行进度 ", font=("微软雅黑", 9, "bold"), padx=15, pady=10)
        self.frame_progress.pack(fill="x", padx=25, pady=10)
        
        self.label_counter = tk.Label(self.frame_progress, text="等待启动...", font=("微软雅黑", 10))
        self.label_counter.pack(anchor="w")
        self.label_eta = tk.Label(self.frame_progress, text="预估剩余时间: --", font=("微软雅黑", 10), fg="#004B87")
        self.label_eta.pack(anchor="w", pady=(2, 8))
        
        self.progress_bar = ttk.Progressbar(self.frame_progress, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x")

        self.label_status = tk.Label(window, text="💡 状态: 准备就绪，首次使用请配置密钥并保存。", font=("微软雅黑", 10), fg="#333333", pady=5)
        self.label_status.pack()

        # 4. 🚀 启动大按钮
        self.btn_start = tk.Button(window, text="🚀 启动云端高并发对账", command=self.start_async_thread, font=("微软雅黑", 12, "bold"), bg="#0078D4", fg="white", width=25, height=2)
        self.btn_start.pack(pady=5)

        # 5. ⚖️ 严谨的法律免责声明面板
        frame_disclaimer = tk.LabelFrame(window, text=" ⚖️ 法律与合规免责声明 ", font=("微软雅黑", 9, "bold"), fg="#D47A00", padx=10, pady=8)
        frame_disclaimer.pack(fill="x", padx=25, pady=10)
        disclaimer_text = "提示：本工具仅限专机内部效率比对使用。用户向云端传输截图时，请确保已脱敏或获取了利害关系人（如第三方收款人）的合规合法授权。因存储不当、明文外传导致的信息泄露风险由操作方承担，开发者不对财务账目真实性及审计合规结果承担任何法律责任。"
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
                    data = json.load(f)
                    self.entry_id.insert(0, data.get("secret_id", ""))
                    self.entry_key.insert(0, data.get("secret_key", ""))
            except: pass

    def save_credentials(self):
        s_id = self.entry_id.get().strip()
        s_key = self.entry_key.get().strip()
        if not s_id or not s_key:
            messagebox.showwarning("提示", "SecretId 或 SecretKey 不能为空！")
            return
        try:
            with open(CRED_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"secret_id": s_id, "secret_key": s_key}, f, indent=4)
            messagebox.showinfo("成功", "企业微信 OCR 密钥配置已安全保存！")
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")

    def start_async_thread(self):
        t = threading.Thread(target=self.run_async_loop_worker)
        t.daemon = True
        t.start()

    def convert_to_hms(self, seconds):
        hrs, mins, secs = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    def run_async_loop_worker(self):
        target_dir = os.path.normpath(self.entry_path.get().strip())
        s_id = self.entry_id.get().strip()
        s_key = self.entry_key.get().strip()

        if not s_id or not s_key or not target_dir or not os.path.exists(target_dir):
            messagebox.showerror("错误", "请检查密钥是否填写并保存，或文件夹路径是否有效！")
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
        self.label_status.config(text="⏳ 异步高并发网络流初始化中...", fg="#D47A00")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        start_recognition_time = time.time()
        raw_outputs = []

        async def master_task():
            # 1. 改造异步任务：让它把图片路径 (img_p) 绑定作为元组传入
            async def wrapped_task(img_p):
                res = await core_logic.async_ocr_request(img_p, s_id, s_key)
                return img_p, res  # 执行完毕后，把对应的物理路径原封不动打包带回

            tasks = [wrapped_task(img_p) for img_p in all_images_flat]
            
            for next_done_coro in asyncio.as_completed(tasks):
                # 2. 这里的 img_abs_path 永远是跟结果绝对绑定的，绝不会再发生错位
                img_abs_path, ocr_list = await next_done_coro
                img_base_name, _ = os.path.splitext(os.path.basename(img_abs_path))
                raw_outputs.append((img_base_name, ocr_list))
                
                processed_count = len(raw_outputs)
                remaining_count = total_images - processed_count
                elapsed = time.time() - start_recognition_time
                estimated_remaining = (elapsed / processed_count) * remaining_count if processed_count else 0
                eta_str = "已完成" if processed_count == total_images else self.convert_to_hms(estimated_remaining)

                self.progress_bar["value"] = processed_count
                self.label_counter.config(text=f"已处理: {processed_count} 张 / 剩余: {remaining_count} 张 (总计 {total_images} 张)")
                self.label_eta.config(text=f"⏳ 预计还需要等待: {eta_str}")
                self.window.update()

        loop.run_until_complete(master_task())
        loop.close()

        hms_duration = self.convert_to_hms(time.time() - start_recognition_time)
        ocr_result_registry = {name: ocr for name, ocr in raw_outputs if ocr}
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
            
            # 使用彻底安全的 len() 函数替代，绝对不会再破坏 Markdown
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
        self.label_status.config(text=f"✅ 成功！耗时: {hms_duration}", fg="green")
        
        # 🔗 动态获取当前处理的文件夹路径
        target_dir = os.path.normpath(self.entry_path.get().strip())
        sub_folder_name = os.path.basename(target_dir) or "账单"
        excel_name = f"{sub_folder_name}批量账单.xlsx"

        # =====================================================================
        # ✨ 1. 创建位于主界面正中间的自定义 Tkinter 弹窗
        # =====================================================================
        dialog = tk.Toplevel(self.window)
        dialog.title("🎉 对账任务完成")
        dialog.configure(bg="#F3F3F3")
        dialog.resizable(False, False)
        
        # 🔒 开启强制模态聚焦（不处理完这个弹窗，用户无法点击主界面）
        dialog.transient(self.window)
        dialog.grab_set()

        # 📐 精密坐标计算：让弹窗精准显示在主界面的正中央
        dialog_width, dialog_height = 420, 200
        
        # 获取主窗口当前的尺寸与屏幕物理坐标
        self.window.update_idletasks()
        main_w = self.window.winfo_width()
        main_h = self.window.winfo_height()
        main_x = self.window.winfo_x()
        main_y = self.window.winfo_y()
        
        # 计算居中坐标
        pos_x = main_x + (main_w - dialog_width) // 2
        pos_y = main_y + (main_h - dialog_height) // 2
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")

        # =====================================================================
        # 📝 2. 核心文本显示区（融合您提供的 msg_text 与布局）
        # =====================================================================
        main_frame = tk.Frame(dialog, bg="#F3F3F3", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)

        # 加个显眼的任务成功大标题
        tk.Label(main_frame, text="⚡ 云端高并发对账全部结束！", font=("微软雅黑", 11, "bold"), fg="#0078D4", bg="#F3F3F3").grid(row=0, column=1, sticky="w", pady=(0, 4))

        # 精准还原您要求的 msg_text 提示语
        msg_text = f"对账结果已成功保存并生成在当前图片文件夹：\n👉 {excel_name}\n⏱️ 总计耗时：{hms_duration}"
        tk.Label(main_frame, text=msg_text, font=("微软雅黑", 10), justify="left", fg="#333333", bg="#F3F3F3").grid(row=1, column=1, sticky="w", pady=(8, 0))
        
        # =====================================================================
        # 🔘 3. 底部按钮控制区（完美还原绿色打开文件夹按钮 + 取消按钮）
        # =====================================================================
        btn_frame = tk.Frame(dialog, pady=15, bg="#F3F3F3")
        btn_frame.pack(fill="x", side="bottom")

        # 定义唤起资源管理器的物理调用
        def on_open_folder(path):
            try:
                if os.path.exists(path):
                    os.startfile(path)
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹: {e}")

        # 右侧 1：绿色“📂 打开文件夹”按钮（点击后打开目录并自动销毁弹窗）
        btn_open = tk.Button(
            btn_frame, 
            text="📂 打开文件夹", 
            font=("微软雅黑", 10, "bold"), 
            bg="#107C41", 
            fg="white", 
            padx=15, 
            pady=3,
            command=lambda: [on_open_folder(target_dir), dialog.destroy()]
        )
        btn_open.pack(side="right", padx=(10, 20))

        # 右侧 2：取消按钮
        btn_cancel = tk.Button(
            btn_frame, 
            text=" 取消 ", 
            font=("微软雅黑", 10), 
            bg="#E1E1E1", 
            fg="#333333", 
            padx=15, 
            pady=3,
            command=dialog.destroy
        )
        btn_cancel.pack(side="right")


if __name__ == "__main__":
    root = tk.Tk()
    app = BillOcrGui(root)
    root.mainloop()
