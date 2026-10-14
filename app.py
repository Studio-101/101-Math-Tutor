import os
import sys
import uuid
import io
from pathlib import Path
from PIL import Image, ImageOps
import streamlit as st
from streamlit_cropper import st_cropper

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.gemini_client import GeminiTutorEngine
from core.logger import TrajectoryLogger
from core.sync_server import (
    get_sync_url,
    generate_qr_code_image,
    pop_latest_upload,
    start_sync_server,
    _SESSIONS,
    _SESSIONS_LOCK,
)

# ---------------------------------------------------------
# 外部連結設定 (若未來要更換教學影片，直接修改此變數即可)
# ---------------------------------------------------------
PROJECT_VIDEO_URL = "https://youtu.be/ABUd4-0TR7w"

# ---------------------------------------------------------
# Page Configuration & Styling
# ---------------------------------------------------------
st.set_page_config(
    page_title="101事務所數學家教",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 手機上傳模式：雲端部署時 QR Code 會指向 ?upload=<session_id>
upload_session_id = st.query_params.get("upload")
if upload_session_id:
    mobile_file = st.file_uploader("拍照或選擇圖片", type=["png", "jpg", "jpeg", "webp"])
    mobile_note = st.text_input("備註（選填）")
    if mobile_file and st.button("傳送給電腦", use_container_width=True):
        with _SESSIONS_LOCK:
            _SESSIONS.setdefault(upload_session_id, []).append({
                "image_bytes": mobile_file.getvalue(),
                "note": mobile_note,
            })
        st.success("已傳送！請回到電腦畫面。")
    st.stop()

st.markdown(
    """
    <style>
    .workflow-badge {
        display: inline-block;
        background-color: rgba(99, 102, 241, 0.15);
        color: #818CF8;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "pending_attachment" not in st.session_state:
    st.session_state.pending_attachment = None

if "problem_text" not in st.session_state:
    st.session_state.problem_text = ""

if "image_bytes" not in st.session_state:
    st.session_state.image_bytes = None

if "coordinator_response" not in st.session_state:
    st.session_state.coordinator_response = ""

if "solver_report" not in st.session_state:
    st.session_state.solver_report = ""

if "solver_logs" not in st.session_state:
    st.session_state.solver_logs = []

if "logger" not in st.session_state:
    st.session_state.logger = TrajectoryLogger()


if "sync_session_id" not in st.session_state:
    st.session_state.sync_session_id = uuid.uuid4().hex[:8]

if "draft_rotation" not in st.session_state:
    st.session_state.draft_rotation = 0

if "pc_rotation" not in st.session_state:
    st.session_state.pc_rotation = 0

if "waiting_for_tutor" not in st.session_state:
    st.session_state.waiting_for_tutor = False


def reset_session():
    st.session_state.chat_history = []
    st.session_state.pending_attachment = None
    st.session_state.problem_text = ""
    st.session_state.image_bytes = None
    st.session_state.coordinator_response = ""
    st.session_state.solver_report = ""
    st.session_state.solver_logs = []
    st.session_state.logger = TrajectoryLogger()
    st.session_state.sync_session_id = uuid.uuid4().hex[:8]
    st.session_state.draft_rotation = 0
    st.session_state.pc_rotation = 0
    st.session_state.waiting_for_tutor = False
    if "incoming_mobile_draft" in st.session_state:
        del st.session_state.incoming_mobile_draft


def format_friendly_error(e: Exception, action_desc: str = "解題") -> str:
    err_str = str(e)
    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
        return (
            f"⚠️ **{action_desc}中斷：Gemini API 額度或頻率已達上限**\n\n"
            "Google 免費金鑰有每分鐘請求頻率上限（RPM）。\n\n"
            "**建議排解方式：**\n"
            "1. 請稍候約 30～60 秒後，在下方再次發送訊息重試。\n"
            "2. 或至左側側邊欄更換另一組免費 Gemini API Key。\n"
            "3. 亦可在側邊欄嘗試切換模型（如 Gemini 3.8 Flash）。"
        )
    elif "API_KEY_INVALID" in err_str or "api key not valid" in err_str.lower() or "invalid api key" in err_str.lower():
        return (
            f"⚠️ **{action_desc}中斷：Gemini API Key 無效**\n\n"
            "請檢查左側側邊欄輸入的金鑰是否正確無誤（確認前後無多餘空格）。"
        )
    else:
        return (
            f"⚠️ **{action_desc}過程發生異常：**\n\n"
            f"> {err_str}\n\n"
            "建議稍候片刻再試，或點擊左側「🔄 開啟新題目 / 重設對話」重新開始。"
        )


# ---------------------------------------------------------
# Sidebar Configuration
# ---------------------------------------------------------
with st.sidebar:
    st.title("🎓 系統設定與資訊")

    api_key_input = st.text_input(
        "Gemini API Key",
        value=os.environ.get("GEMINI_API_KEY", ""),
        type="password",
        help="預設使用環境變數中的 GEMINI_API_KEY，亦可自行貼上。",
    )
    st.caption(
        "🔒 **安全與計費提醒**：\n"
        "- 建議使用 **未綁定信用卡** 的純免費專案金鑰，安全無扣款風險（額度耗盡只會暫停，絕無費用）。\n"
        "- 若使用已綁卡付費（Pay-as-you-go）之金鑰，請自行留意 Google 帳單用量。"
    )

    MODEL_OPTIONS = {
        "gemini-3.8-flash": "Gemini 3.8 Flash (全方位協助・推薦)",
        "gemini-4-argon": "Gemini 4 Argon (新模型・複雜任務)",
        "gemini-3.1-pro-preview": "Gemini 3.1 Pro (進階推論)",
        "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite (回覆最快)",
    }

    selected_model = st.selectbox(
        "推理模型 (Model)",
        options=list(MODEL_OPTIONS.keys()),
        format_func=lambda m: MODEL_OPTIONS.get(m, m),
        index=0,
        help="推薦使用 Gemini 3.8 Flash 或 3.7 Flash，擁有最新推理能力與極佳的代碼生成精確度。",
    )

    st.markdown("---")
    show_debug_audit = st.checkbox(
        "🛠️ 顯示幕後雙軌驗證報告",
        value=False,
        help="勾選後可在主畫面上方展開檢視 AI 雙軌解題驗證結論與 Python 運算腳本。",
    )

    st.markdown("---")
    if st.button("🔄 開啟新題目 / 重設對話", use_container_width=True):
        reset_session()
        st.rerun()

    st.markdown("---")
    st.markdown("### 🎬 幕後製作教學")
    st.caption("想了解這套 AI 雙軌家教系統是如何打造的？")
    st.link_button("📺 觀看 YouTube 完整解密", PROJECT_VIDEO_URL, use_container_width=True)

# Check Engine readiness
if not api_key_input:
    col_t1, col_t2 = st.columns([3, 1], vertical_alignment="bottom")
    with col_t1:
        st.title("🎓 101事務所數學家教")
    with col_t2:
        st.link_button("🎬 觀看製作影片", PROJECT_VIDEO_URL, use_container_width=True)
    st.caption("你的專屬學測數學家教，帶你一步步想通每道難題")

    st.warning("⚠️ 尚未偵測到 Gemini API Key，請在左側側邊欄輸入金鑰以開始使用。")

    with st.container(border=True):
        st.markdown("### 💡 如何免費取得 Gemini API Key？（約 30 秒完成）")
        st.markdown(
            """
            1. 前往 **[Google AI Studio (aistudio.google.com)](https://aistudio.google.com/)**。
            2. 使用 Google 帳號登入後，點擊 **「Get API key」** ➔ **「Create API key」**。
            3. 複製產生的金鑰，貼入左側側邊欄的 **「Gemini API Key」** 欄位即可開始提問！
            
            ---
            
            🔒 **重要計費安全提醒**：
            - **建議使用純免費專案**：Google AI Studio 預設提供的免費專案（Free Tier）**完全不需要綁定信用卡**，每日每分鐘皆有免費額度，額度耗盡僅會暫時停止回應，**保證絕不扣款**。
            - **注意付費專案用量**：若您使用的是已在 Google Cloud 綁定信用卡開啟扣款（Pay-as-you-go）的專案金鑰，解題過程中的視覺辨識與多輪對話將會計入用量，請務必自行留意 Google 雲端帳單費用。
            """
        )
    st.stop()

try:
    engine = GeminiTutorEngine(api_key=api_key_input, model=selected_model)
except Exception as e:
    st.error(f"引擎初始化失敗：{str(e)}")
    st.stop()

# Auto-start Mobile Sync Server (Port 8502)
start_sync_server(port=8502)

# ---------------------------------------------------------
# Silent Background Listener for Incoming Mobile Photos
# ---------------------------------------------------------
@st.fragment(run_every="2s")
def mobile_sync_listener():
    upload = pop_latest_upload(st.session_state.sync_session_id)
    if upload:
        st.session_state.incoming_mobile_draft = upload
        st.rerun()

mobile_sync_listener()

# ---------------------------------------------------------
# Dialog: Crop & Attach Incoming Mobile Photo
# ---------------------------------------------------------
@st.dialog("📸 收到手機拍傳照片！請確認裁剪範圍", width="large")
def crop_incoming_mobile_dialog():
    draft = st.session_state.incoming_mobile_draft
    st.caption("📱 照片已由手機同步至電腦。請在下方電腦大螢幕調整方向或拖曳選框裁剪，去除桌面與陰影雜訊：")

    col_dm1, col_dm2, col_dr1, col_dr2 = st.columns([2, 1, 1, 1])
    with col_dm1:
        enable_draft_crop = st.checkbox("啟用裁剪 (建議框選題目或算式主體)", value=True, key="cb_incoming_draft_crop")
    with col_dm2:
        if st.session_state.draft_rotation != 0:
            st.caption(f"已旋轉：{st.session_state.draft_rotation}°")
    with col_dr1:
        if st.button("↺ 向左轉 90°", key="btn_rot_left_draft", use_container_width=True):
            st.session_state.draft_rotation = (st.session_state.draft_rotation - 90) % 360
            st.rerun()
    with col_dr2:
        if st.button("↻ 向右轉 90°", key="btn_rot_right_draft", use_container_width=True):
            st.session_state.draft_rotation = (st.session_state.draft_rotation + 90) % 360
            st.rerun()

    try:
        pil_incoming = Image.open(io.BytesIO(draft["image_bytes"]))
        pil_incoming = ImageOps.exif_transpose(pil_incoming)
        if st.session_state.draft_rotation != 0:
            pil_incoming = pil_incoming.rotate(-st.session_state.draft_rotation, expand=True)

        if enable_draft_crop:
            col_m1, col_m2 = st.columns([3, 2])
            with col_m1:
                st.markdown("**拖曳方框調整裁剪範圍：**")
                cropped_incoming = st_cropper(
                    pil_incoming,
                    realtime_update=True,
                    box_color="#4F46E5",
                    aspect_ratio=None,
                    key=f"cropper_incoming_mobile_{st.session_state.draft_rotation}",
                )
            with col_m2:
                st.markdown("**裁剪預覽：**")
                st.image(cropped_incoming, use_container_width=True)
            buf = io.BytesIO()
            cropped_incoming.save(buf, format="JPEG", quality=95)
            final_draft_bytes = buf.getvalue()
        else:
            st.image(pil_incoming, caption="原始手機照片（未裁剪）", width=360)
            buf = io.BytesIO()
            pil_incoming.save(buf, format="JPEG", quality=95)
            final_draft_bytes = buf.getvalue()
    except Exception as e:
        st.warning(f"圖片處理提示：{str(e)}")
        final_draft_bytes = draft["image_bytes"]

    col_sub1, col_sub2 = st.columns([2, 1])
    with col_sub1:
        if st.button("📎 加入對話附件 (掛載至輸入框)", type="primary", use_container_width=True, key="btn_attach_mobile_draft"):
            st.session_state.pending_attachment = final_draft_bytes
            del st.session_state.incoming_mobile_draft
            st.session_state.draft_rotation = 0
            st.rerun()
    with col_sub2:
        if st.button("❌ 放棄此張照片", use_container_width=True, key="btn_cancel_draft"):
            del st.session_state.incoming_mobile_draft
            st.session_state.draft_rotation = 0
            st.rerun()

if "incoming_mobile_draft" in st.session_state and st.session_state.incoming_mobile_draft:
    crop_incoming_mobile_dialog()

# ---------------------------------------------------------
# Dialog: Upload Photo via ➕ Button (Mobile QR / PC File)
# ---------------------------------------------------------
@st.dialog("📷 上傳照片 (題目或草稿)", width="large")
def upload_draft_dialog():
    tab_mobile, tab_pc = st.tabs(["📲 手機拍照即時上傳", "📁 從電腦選擇檔案"])

    with tab_mobile:
        host = st.context.headers.get("Host", "")
        if host.startswith(("localhost", "127.0.0.1")):
            sync_url_tutor = get_sync_url(st.session_state.sync_session_id)
        else:
            sync_url_tutor = f"https://{host}/?upload={st.session_state.sync_session_id}"
        qr_bytes_tutor = generate_qr_code_image(sync_url_tutor)
        col_tqr, col_tdesc = st.columns([1, 2])
        with col_tqr:
            st.image(qr_bytes_tutor, width=200, caption="手機相機掃碼直接拍照")
        with col_tdesc:
            st.markdown("#### 📐 手機即拍即傳助手")
            st.markdown(
                """
                1. **免打字隨手拍**：用手機相機掃描左側 QR 碼，開啟極簡拍照畫面。
                2. **拍照並傳送**：拍下題目或手寫算式草稿照片，點擊「傳送給電腦」。
                3. **電腦端接收**：手機傳送後請關閉此視窗，電腦大螢幕將在 2 秒內自動跳出裁剪工具供您調整並掛載至對話框！
                """
            )
            st.caption(f"手機直連網址：{sync_url_tutor}")

    with tab_pc:
        pc_upload = st.file_uploader(
            "選擇電腦中的圖片檔案 (JPG / PNG / WEBP)",
            type=["png", "jpg", "jpeg", "webp"],
            key="dialog_pc_draft_file",
        )
        pc_final_bytes = None
        if pc_upload:
            col_pctl1, col_pctl2, col_prot1, col_prot2 = st.columns([2, 1, 1, 1])
            with col_pctl1:
                enable_pc_crop = st.checkbox("啟用草稿裁剪", value=True, key="cb_dialog_pc_crop")
            with col_pctl2:
                if st.session_state.pc_rotation != 0:
                    st.caption(f"已旋轉：{st.session_state.pc_rotation}°")
            with col_prot1:
                if st.button("↺ 向左轉 90°", key="btn_dialog_rot_left_pc", use_container_width=True):
                    st.session_state.pc_rotation = (st.session_state.pc_rotation - 90) % 360
                    st.rerun()
            with col_prot2:
                if st.button("↻ 向右轉 90°", key="btn_dialog_rot_right_pc", use_container_width=True):
                    st.session_state.pc_rotation = (st.session_state.pc_rotation + 90) % 360
                    st.rerun()

            try:
                pil_pc = Image.open(pc_upload)
                pil_pc = ImageOps.exif_transpose(pil_pc)
                if st.session_state.pc_rotation != 0:
                    pil_pc = pil_pc.rotate(-st.session_state.pc_rotation, expand=True)

                if enable_pc_crop:
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        st.markdown("**拖曳選取草稿範圍：**")
                        cropped_pc = st_cropper(
                            pil_pc,
                            realtime_update=True,
                            box_color="#4F46E5",
                            aspect_ratio=None,
                            key=f"cropper_dialog_pc_{st.session_state.pc_rotation}",
                        )
                    with col_p2:
                        st.markdown("**裁剪預覽：**")
                        st.image(cropped_pc, use_container_width=True)
                    buf = io.BytesIO()
                    cropped_pc.save(buf, format="JPEG", quality=95)
                    pc_final_bytes = buf.getvalue()
                else:
                    st.image(pil_pc, caption="旋轉後圖片（未裁剪）", width=360)
                    buf = io.BytesIO()
                    pil_pc.save(buf, format="JPEG", quality=95)
                    pc_final_bytes = buf.getvalue()
            except Exception:
                pc_final_bytes = pc_upload.getvalue()

            if st.button("📎 加入對話附件 (掛載至輸入框)", key="btn_dialog_attach_pc_draft", type="primary", use_container_width=True):
                if pc_final_bytes:
                    st.session_state.pending_attachment = pc_final_bytes
                    st.session_state.pc_rotation = 0
                    st.rerun()

# ---------------------------------------------------------
# Main Page: Title & Audit Expanders
# ---------------------------------------------------------
col_main_t1, col_main_t2 = st.columns([3, 1], vertical_alignment="bottom")
with col_main_t1:
    st.title("🎓 101事務所數學家教")
with col_main_t2:
    st.link_button("🎬 觀看製作影片", PROJECT_VIDEO_URL, use_container_width=True)
st.caption("你的專屬學測數學家教，帶你一步步想通每道難題")

# Top Collapsible Cards (Available after problem is verified)
if st.session_state.get("coordinator_response"):
    with st.expander("📝 查看本題已知條件與求解目標", expanded=False):
        st.markdown(st.session_state.coordinator_response)

if show_debug_audit and st.session_state.get("solver_report"):
    with st.expander("🔍 檢視 AI 幕後雙軌驗證報告 (點擊展開)", expanded=False):
        st.markdown("#### 內部驗證結論報告")
        st.markdown(st.session_state.solver_report)

        if st.session_state.solver_logs:
            st.markdown("---")
            st.markdown("#### 後台 Python (SymPy) 執行腳本與輸出記錄")
            for idx, log in enumerate(st.session_state.solver_logs, 1):
                status_icon = "✅ 執行成功" if log["success"] else "❌ 執行失敗"
                st.markdown(f"**驗證腳本 #{idx} ({status_icon})**")
                st.code(log["code"], language="python")
                st.markdown("**終端機真實輸出 (Stdout / Stderr)：**")
                st.text(log["output"] if log["output"] else "(無輸出內容)")
        else:
            st.info("雙軌驗證已由模型完成比對。")

# ---------------------------------------------------------
# Chat Conversation Area
# ---------------------------------------------------------
if len(st.session_state.chat_history) == 0:
    # Clean Welcoming & Preset Examples
    with st.container(border=True):
        st.markdown("### 👋 歡迎來到 101事務所數學家教！")
        st.markdown(
            "我是你的專屬數學家教。隨時將你卡住的數學題目**拍照**或**打字**發送給我，\n"
            "我會先為你仔細拆解條件，並像家教老師一樣一步步引導你想通算式！\n\n"
            "💡 **作答提示**：在最下方對話框輸入文字，或點擊左下角 `➕` 拍照／上傳題目照片（支援附帶備註，例如「我只想問第 (2) 小題」）。"
        )
        st.caption("或者點選下方預設題目快速體驗：")
        col_demo1, col_demo2 = st.columns(2)
        with col_demo1:
            if st.button("📌 課本例題：空間四角錐體積", use_container_width=True):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": (
                        "底面為邊長 4 的正方形 ABCD，頂點為 E。側棱長 EA = EB = 3，EC = ED = 5。"
                        "F 為邊 AB 的中點，求四角錐 E-ABCD 的體積。"
                    ),
                })
                st.session_state.waiting_for_tutor = True
                st.rerun()
        with col_demo2:
            if st.button("📌 幾何基本題：直角三角形求斜邊", use_container_width=True):
                st.session_state.chat_history.append({
                    "role": "user",
                    "content": "已知一個直角三角形兩股長分別為 3 和 4，求斜邊長度。",
                })
                st.session_state.waiting_for_tutor = True
                st.rerun()
else:
    # Render full chat conversation
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            if message.get("image_bytes"):
                st.image(message["image_bytes"], caption="📷 上傳照片", width=360)
            st.markdown(message["content"])

# ---------------------------------------------------------
# Tutor Processing & Streaming (Main Body)
# ---------------------------------------------------------
if st.session_state.get("waiting_for_tutor", False):
    with st.chat_message("assistant"):
        if len(st.session_state.chat_history) == 1:
            # First turn: Run Coordinator -> SymPy Solver -> SHAPE Tutor opening
            first_user_msg = st.session_state.chat_history[0]
            u_text = first_user_msg.get("content", "")
            u_img = first_user_msg.get("image_bytes")

            with st.status("🧑‍🏫 老師正在為你審題並準備引導...", expanded=True) as status:
                status.write("📖 正在仔細閱讀題目與梳理已知條件...")
                try:
                    coord_result = engine.coordinate_problem(
                        text_input=u_text,
                        image_bytes=u_img,
                        logger=st.session_state.logger,
                    )
                    st.session_state.problem_text = u_text
                    st.session_state.image_bytes = u_img
                    st.session_state.coordinator_response = coord_result

                    status.write("📐 老師正在計算確認解題路徑與答案...")
                    report, logs = engine.solve_with_verification(
                        coord_result,
                        logger=st.session_state.logger,
                    )
                    st.session_state.solver_report = report
                    st.session_state.solver_logs = logs

                    status.write("💡 正在準備引導你的思考方向...")
                    first_msg = engine.start_tutoring_first_message(
                        coord_result,
                        report,
                        logger=st.session_state.logger,
                    )


                    status.update(label="✅ 老師已就緒，我們開始吧！", state="complete", expanded=False)

                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": first_msg,
                    })
                except Exception as e:
                    status.update(label="❌ 處理中斷", state="error", expanded=True)
                    friendly_error = format_friendly_error(e, action_desc="審題與驗證")
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": friendly_error,
                    })
                finally:
                    st.session_state.waiting_for_tutor = False
            st.rerun()
        else:
            # Subsequent turns: Conversational micro-scaffolding
            with st.spinner("家教正在審閱你的回答與手寫草稿..."):
                try:
                    tutor_reply = engine.continue_tutoring_with_history(
                        st.session_state.coordinator_response,
                        st.session_state.solver_report,
                        st.session_state.chat_history,
                        logger=st.session_state.logger,
                    )
                    st.markdown(tutor_reply)
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": tutor_reply,
                    })
                except Exception as e:
                    friendly_error = format_friendly_error(e, action_desc="對話引導")
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": friendly_error,
                    })
                finally:
                    st.session_state.waiting_for_tutor = False
            st.rerun()

# ---------------------------------------------------------
# Bottom Bar: Attachment Chip & Input Controls
# ---------------------------------------------------------
with st.bottom:
    # 1. Pending Attachment Chip (if photo is attached)
    if st.session_state.get("pending_attachment"):
        with st.container(border=True):
            col_chip_img, col_chip_info, col_chip_btn1, col_chip_btn2 = st.columns([1, 5, 2, 1], vertical_alignment="center")
            with col_chip_img:
                st.image(st.session_state.pending_attachment, width=70)
            with col_chip_info:
                st.markdown("**📎 已附加照片**")
                st.caption("可於下方輸入文字說明，按 Enter 一併發送；或直接點擊右側送出")
            with col_chip_btn1:
                if st.button("🚀 送出照片", key="btn_send_attachment_alone", type="primary", use_container_width=True, disabled=st.session_state.get("waiting_for_tutor", False)):
                    st.session_state.chat_history.append({
                        "role": "user",
                        "content": "（已上傳照片）",
                        "image_bytes": st.session_state.pending_attachment,
                    })
                    st.session_state.pending_attachment = None
                    st.session_state.waiting_for_tutor = True
                    st.rerun()
            with col_chip_btn2:
                if st.button("✕", help="移除此照片附件", key="btn_remove_attachment", use_container_width=True):
                    st.session_state.pending_attachment = None
                    st.rerun()

    # 2. Main Chat Input Row (➕ Button + Text Input)
    col_add, col_input = st.columns([1, 18], vertical_alignment="bottom")
    with col_add:
        if st.button(
            "➕",
            help="拍照或上傳照片（支援手機 QR Code 拍照與電腦檔案）",
            use_container_width=True,
            key="btn_plus_upload",
            disabled=st.session_state.get("waiting_for_tutor", False),
        ):
            upload_draft_dialog()
    with col_input:
        prompt_placeholder = "請在此輸入題目或作答文字...（可點擊左側 ➕ 上傳題目或草稿照片）"
        if student_input := st.chat_input(
            prompt_placeholder,
            disabled=st.session_state.get("waiting_for_tutor", False),
        ):
            msg = {
                "role": "user",
                "content": student_input,
            }
            if st.session_state.get("pending_attachment"):
                msg["image_bytes"] = st.session_state.pending_attachment
                st.session_state.pending_attachment = None
            st.session_state.chat_history.append(msg)
            st.session_state.waiting_for_tutor = True
            st.rerun()
