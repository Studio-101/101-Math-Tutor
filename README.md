# 🎓 101事務所數學家教 (101 Math Tutor)

> 專為台灣高中與學測 (GSAT) 數學設計的 **AI 雙軌驗證 × 碎步鷹架引導家教系統**。  
> 告別傳統 LLM 解題的「心算幻覺、算錯答案、直接爆雷算式」問題！

[![YouTube Video](https://img.shields.io/badge/YouTube-幕後製作解密影片-red?logo=youtube)](https://youtu.be/ABUd4-0TR7w)
[![Streamlit](https://img.shields.io/badge/Framework-Streamlit-FF4B4B?logo=streamlit)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://python.org)

---

## 📺 幕後製作教學影片
想了解這套「雙軌驗證 + 碎步鷹架」家教系統是如何從零打造的嗎？  
👉 **[點此觀看 YouTube 完整解密影片](https://youtu.be/ABUd4-0TR7w)**

---

## ✨ 核心特色與架構

本系統採用「三權分立」的 Agentic 技能協調架構：

```text
               ┌───────────────────────────────┐
               │    tutor_coordinator 前台掛號  │
               │   (文字/照片多模態題意確認與派工)   │
               └──────────────┬────────────────┘
                              │
                    確認題意無誤，派發解題任務
                              ▼
               ┌───────────────────────────────┐
               │      math_solver 解題引擎      │
               │  (Python + SymPy 雙軌獨立演算) │
               └──────────────┬────────────────┘
                              │
                    雙軌比對一致，產出內部驗證報告
                              ▼
               ┌───────────────────────────────┐
               │     shape_tutor 鷹架教學      │
               │  (SHAPE 碎步引導、絕不直接給答案)│
               └───────────────────────────────┘
```

1. **`tutor_coordinator`（前台掛號與題意確認）**
   - 負責在對話一開始與學生確認題目條件（支援文字輸入與照片識別）。
   - 嚴格要求學生確認題意後才派工，避免因抄錯題而做白工。

2. **`math_solver`（程式碼雙軌嚴格解題引擎）**
   - 執行 5 階段 MathQ-Verify 驗證題目合法性與完備性。
   - 自主撰寫 Python 腳本，透過兩種獨立的方法（如符號運算 vs. 窮舉/代入檢驗）進行雙軌運算。
   - **嚴禁心算臆測**：只有兩軌結果比對完全一致才產出內部解題報告。

3. **`shape_tutor`（SHAPE 碎步鷹架教學家教）**
   - 站在第一線與學生對話，語氣溫暖耐心。
   - 嚴格依照 `math_solver` 的分步報告進行引導，一次只推進一步（每次 3 句話以內 + 引導問句）。
   - **教學不越獄**：學生思考前絕不直接或變相透露最終答案。

4. **📱 手機拍照即時同步**
   - 電腦端即時生成 QR Code，手機掃碼即可直接拍照上傳題目或手寫算草。
   - 電腦端內建圖片旋轉與選區裁剪工具。

5. **純文字排版規範**
   - 全程使用純文字與常見 Unicode 數學符號（如 √, ², ×, ÷, 1/2），**絕對避免使用 LaTeX**，確保任何終端或瀏覽器皆能清晰閱讀。

---

## 🚀 快速開始 (Quick Start)

### 1. 複製專案與安裝依賴

```bash
git clone https://github.com/Studio-101/101-Math-Tutor.git
cd 101-Math-Tutor

# 安裝 Python 依賴套件
pip install -r requirements.txt
```

### 2. 啟動 Web 應用程式

```bash
streamlit run app.py
```
啟動後，瀏覽器將自動開啟 `http://localhost:8501`。

### 3. 設定 Gemini API Key
本專案支援 Google Gemini 最新次世代推理模型（推薦使用 `Gemini 3.8 Flash` 或 `Gemini 3.7 Flash`）：
1. 前往 **[Google AI Studio (aistudio.google.com)](https://aistudio.google.com/)** 免費取得 API Key（約 30 秒完成）。
2. 在網頁左側側邊欄貼上金鑰，即可開始提問！
3. *安全提醒：Google AI Studio 預設之純免費專案無需綁定信用卡，絕無扣款風險。*

---

## 📂 專案目錄結構

```text
.
├── app.py                     # Streamlit 主程式介面
├── requirements.txt           # Python 依賴套件清單
├── AGENTS.md                  # 全域行為規範 (格式限制與派工準則)
├── README.md                  # 專案說明文件
├── core/
│   ├── gemini_client.py       # Gemini API 呼叫與三階段調度引擎
│   ├── code_runner.py         # 後台安全執行 Python 驗證腳本
│   ├── skills_loader.py       # 自動載入 .agents/skills 角色提示詞
│   ├── sync_server.py         # 手機 QR Code 拍照局域網同步伺服器
│   └── logger.py              # 軌跡日誌工具
└── .agents/
    └── skills/
        ├── tutor_coordinator/ # 前台掛號與題意確認技能
        ├── math_solver/       # 雙軌驗證嚴格解題技能
        └── shape_tutor/       # SHAPE 碎步鷹架教學技能
```

---

## 📄 授權條款 (License)

本專案採用 [MIT License](LICENSE) 授權。歡迎自由學習、研究與二次開發！
