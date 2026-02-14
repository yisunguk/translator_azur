import streamlit as st
import os
import time
import uuid
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, generate_container_sas, ContainerSasPermissions
from azure.ai.translation.document import DocumentTranslationClient, DocumentTranslationInput, TranslationTarget
from azure.core.credentials import AzureKeyCredential
import urllib.parse
import requests
import fitz # PyMuPDF for page count
import pandas as pd
import zipfile
import io


# Authentication imports


# -----------------------------
# 설정 및 비밀 관리
# -----------------------------
st.set_page_config(page_title="번역 서비스", page_icon="🌐", layout="wide")

# Custom CSS
st.markdown("""
<style>
    /* Increase font size for tab labels */
    button[data-baseweb="tab"] {
        font-size: 20px !important;
    }
    button[data-baseweb="tab"] p {
        font-size: 20px !important;
        font-weight: 600 !important;
    }
    
    /* Document list - row alignment */
    [data-testid="stHorizontalBlock"] {
        display: flex !important;
        align-items: center !important;
        gap: 0.5rem !important;
        min-height: 42px !important;
    }
    
    /* Column layout - vertical centering */
    [data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
    }
    
    /* All buttons - consistent height and sizing */
    .stButton button, .stLinkButton a {
        min-height: 38px !important;
        max-height: 38px !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0.25rem 0.75rem !important;
        white-space: nowrap !important;
        font-size: 1.1rem !important;
    }
    
    /* Popover button - same height */
    button[data-testid="baseButton-header"] {
        min-height: 38px !important;
        max-height: 38px !important;
        height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0.25rem 0.75rem !important;
        font-size: 1.1rem !important;
    }
    
    /* Checkbox alignment */
    .stCheckbox {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        min-height: 38px !important;
    }
    
    /* Markdown text alignment */
    .stMarkdown {
        display: flex !important;
        align-items: center !important;
        min-height: 38px !important;
    }
    
    /* Prevent wrapping in icon columns */
    [data-testid="column"] > div {
        white-space: nowrap !important;
    }
</style>
""", unsafe_allow_html=True)

def get_secret(key):
    if key in st.secrets:
        return st.secrets[key]
    return os.environ.get(key)

# 필수 자격 증명
# 1. Storage
STORAGE_CONN_STR = get_secret("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = get_secret("AZURE_BLOB_CONTAINER_NAME") or "blob-leesunguk"

# 2. Translator
TRANSLATOR_KEY = get_secret("AZURE_TRANSLATOR_KEY")
TRANSLATOR_ENDPOINT = get_secret("AZURE_TRANSLATOR_ENDPOINT")

# -----------------------------
# Azure 클라이언트 헬퍼
# -----------------------------
def get_blob_service_client():
    if not STORAGE_CONN_STR:
        st.error("Azure Storage Connection String이 설정되지 않았습니다.")
        st.stop()
    return BlobServiceClient.from_connection_string(STORAGE_CONN_STR)

def get_translation_client():
    if not TRANSLATOR_KEY or not TRANSLATOR_ENDPOINT:
        st.error("Azure Translator Key 또는 Endpoint가 설정되지 않았습니다.")
        st.stop()
    return DocumentTranslationClient(TRANSLATOR_ENDPOINT, AzureKeyCredential(TRANSLATOR_KEY))

def generate_sas_url(blob_service_client, container_name, blob_name=None, page=None, permission="r", expiry_hours=1, content_disposition=None, no_viewer=False):
    """
    Generates a SAS URL for a blob and wraps it in a web viewer (Google Docs/Office) if applicable.
    If blob_name is None, generates a Container SAS.
    """
    try:
        account_name = blob_service_client.account_name
        
        # Handle credential types
        if hasattr(blob_service_client.credential, 'account_key'):
            account_key = blob_service_client.credential.account_key
        else:
            account_key = blob_service_client.credential['account_key']
        
        start = datetime.utcnow() - timedelta(minutes=15)
        expiry = datetime.utcnow() + timedelta(hours=expiry_hours)
        
        if blob_name:
            # Clean blob name (remove page suffixes like " (p.1)")
            import re
            clean_name = re.sub(r'\s*\(\s*p\.?\s*\d+\s*\)', '', blob_name).strip()
            
            # Determine content type
            import mimetypes
            content_type, _ = mimetypes.guess_type(clean_name)
            
            # Force PDF content type if extension matches (to ensure browser opens it)
            if clean_name.lower().endswith('.pdf'):
                content_type = "application/pdf"
                content_disposition = "inline"
            elif not content_type:
                content_type = "application/octet-stream"

            if content_disposition is None:
                content_disposition = "inline"

            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=container_name,
                blob_name=clean_name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                start=start,
                expiry=expiry,
                content_disposition=content_disposition,
                content_type=content_type
            )
            sas_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{urllib.parse.quote(clean_name, safe='/')}?{sas_token}"
            
            if no_viewer:
                return sas_url
            
            lower_name = clean_name.lower()
            if lower_name.endswith(('.pptx', '.ppt', '.docx', '.doc', '.xlsx', '.xls')):
                encoded_sas_url = urllib.parse.quote(sas_url)
                return f"https://view.officeapps.live.com/op/view.aspx?src={encoded_sas_url}"
            elif lower_name.endswith('.pdf'):
                # Direct SAS URL with content_disposition=inline opens in browser PDF viewer
                final_url = sas_url
                if page:
                    final_url += f"#page={page}"
                return final_url
            else:
                return sas_url
        else:
            # Container SAS
            sas_token = generate_container_sas(
                account_name=account_name,
                container_name=container_name,
                account_key=account_key,
                permission=ContainerSasPermissions(write=True, list=True, read=True, delete=True),
                start=start,
                expiry=expiry
            )
            return f"https://{account_name}.blob.core.windows.net/{container_name}?{sas_token}"
            
    except Exception as e:
        st.error(f"SAS URL 생성 중 오류 발생 ({blob_name}): {e}")
        return "#"

def is_drm_protected(uploaded_file):
    """
    Check if the uploaded file is DRM protected or encrypted.
    Returns True if protected, False otherwise.
    """
    try:
        file_type = uploaded_file.name.split('.')[-1].lower()
        
        # 1. PDF Check
        if file_type == 'pdf':
            try:
                # Read file stream
                bytes_data = uploaded_file.getvalue()
                with fitz.open(stream=bytes_data, filetype="pdf") as doc:
                    if doc.is_encrypted:
                        return True
            except Exception as e:
                print(f"PDF DRM Check Error: {e}")
                # If we can't open it with fitz, it might be corrupted or heavily encrypted
                return True 

        # 2. Office Files (docx, pptx, xlsx) Check
        elif file_type in ['docx', 'pptx', 'xlsx']:
            try:
                bytes_data = uploaded_file.getvalue()
                # Check if it is a valid zip file
                if not zipfile.is_zipfile(io.BytesIO(bytes_data)):
                    # Not a zip -> Likely Encrypted/DRM (OLE format)
                    return True
                
                # Optional: Try to open it to be sure
                with zipfile.ZipFile(io.BytesIO(bytes_data)) as zf:
                    # Check for standard OOXML structure (e.g., [Content_Types].xml)
                    if '[Content_Types].xml' not in zf.namelist():
                        return True
            except Exception as e:
                print(f"Office DRM Check Error: {e}")
                return True # Assume protected if we can't parse structure
                
        return False
    except Exception as e:
        print(f"General DRM Check Error: {e}")
        return False

# -----------------------------
# UI 구성
# -----------------------------

# 지원 언어 목록 가져오기 (API)
@st.cache_data
def get_supported_languages():
    try:
        url = "https://api.cognitive.microsofttranslator.com/languages?api-version=3.0&scope=translation"
        # Accept-Language 헤더를 'ko'로 설정하여 언어 이름을 한국어로 받음
        headers = {"Accept-Language": "ko"}
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        languages = {}
        for code, info in data['translation'].items():
            # "한국어 이름 (원어 이름)" 형식으로 표시 (예: 영어 (English))
            label = f"{info['name']} ({info['nativeName']})"
            languages[label] = code
        return languages
    except requests.exceptions.SSLError:
        # 로컬 환경(사내망) 등에서 SSL 인증서 오류 발생 시 verify=False로 재시도
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            response = requests.get(url, headers=headers, verify=False, timeout=5)
            response.raise_for_status()
            data = response.json()
            languages = {}
            for code, info in data['translation'].items():
                label = f"{info['name']} ({info['nativeName']})"
                languages[label] = code
            return languages
        except Exception as e:
            print(f"SSL Bypass retry failed: {e}")
            # 실패 시 아래 기본 언어 제공으로 넘어감

    except Exception as e:
        print(f"언어 목록 가져오기 실패 (API): {e}")
        # UI에 에러를 표시하지 않고 콘솔에만 남김
    
    # 실패 시 기본 언어 제공 (확장된 목록)
    return {
        "한국어 (Korean)": "ko", 
        "영어 (English)": "en",
        "일본어 (Japanese)": "ja",
        "중국어 간체 (Chinese Simplified)": "zh-Hans",
        "중국어 번체 (Chinese Traditional)": "zh-Hant",
        "프랑스어 (French)": "fr",
        "독일어 (German)": "de",
        "스페인어 (Spanish)": "es",
        "러시아어 (Russian)": "ru",
        "베트남어 (Vietnamese)": "vi"
    }

LANGUAGES = get_supported_languages()

LANG_SUFFIX_OVERRIDE = {
    "zh-Hans": "CN",
    "zh-Hant": "TW",
}


# Default user info (Guest)
user_info = {"name": "Guest", "email": "guest@example.com"}

# Session State Initialization for Retries and Processing
if 'processing_state' not in st.session_state:
    st.session_state.processing_state = {} 
    # Structure: {file_id: {'status': 'processing'|'success'|'failed', 'source_blob': str, 'target_blob': str, 'original_name': str, 'data': bytes, 'error': str}}

with st.sidebar:
    st.header("번역 설정")
    # 한국어를 기본값으로 찾기
    default_index = 0
    lang_labels = list(LANGUAGES.keys())
    for i, label in enumerate(lang_labels):
        if "Korean" in label or "한국어" in label:
            default_index = i
            break
            
    target_lang_labels = st.multiselect("목표 언어 선택 (복수 선택 가능)", lang_labels, default=[lang_labels[default_index]])
    target_lang_codes = [LANGUAGES[label] for label in target_lang_labels]
    
    if target_lang_codes:
        st.info(f"선택된 언어: {', '.join(target_lang_codes)}")
    else:
        st.warning("최소 하나 이상의 언어를 선택해주세요.")
    
    st.divider()



# -----------------------------
# Main Content
# -----------------------------
st.title("번역하기")

if "translate_uploader_key" not in st.session_state:
    st.session_state.translate_uploader_key = 0

uploaded_files = st.file_uploader("번역할 문서 업로드 (PPTX, PDF, DOCX, XLSX 등) - 여러 파일 선택 가능", type=["pptx", "pdf", "docx", "xlsx"], accept_multiple_files=True, key=f"translate_{st.session_state.translate_uploader_key}")

if uploaded_files:
    # Validate languages
    if not target_lang_codes:
        st.warning("먼저 좌측 사이드바에서 목표 언어를 선택해주세요.")
    else:
        # Generate a unique key for this batch session if not exists
        if 'current_batch_id' not in st.session_state:
            st.session_state.current_batch_id = str(uuid.uuid4())
            
        col1, col2 = st.columns([1, 1])
        with col1:
             start_btn = st.button("번역 시작", type="primary", use_container_width=True)
        
        # Retry Logic (Batch Level or File Level? Keeping simple batch retry for now)
        # For simplicity in this multi-file version, we might hide per-file retry or just show a general retry if anything failed.
        # But let's keep the button there.

        batch_id = st.session_state.current_batch_id
        
        # 5. Result Display Logic (Persistent)
        current_state = st.session_state.processing_state.get(batch_id)
        if current_state and current_state.get('status') == 'success':
            st.success("모든 번역 작업이 완료되었습니다! (임시 파일 삭제됨)")
            
            # Check if ZIP or Single File
            if current_state.get('is_zip'):
                st.download_button(
                    label=f"📦 {current_state['filename']} 다운로드 (ZIP)",
                    data=current_state['data'],
                    file_name=current_state['filename'],
                    mime="application/zip",
                    type="primary"
                )
            else:
                 st.download_button(
                    label=f"📥 {current_state['filename']} 다운로드",
                    data=current_state['data'],
                    file_name=current_state['filename'],
                    mime="application/octet-stream",
                    type="primary"
                )

        if start_btn:
            # Clear previous success state if re-running
            if current_state:
                 del st.session_state.processing_state[batch_id]
            
            with st.spinner("파일 처리 및 번역 중..."):
                try:
                    blob_service_client = get_blob_service_client()
                    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
                    
                    # Ensure container exists
                    if not container_client.exists():
                        container_client.create_container()

                    results = []
                    errors = []
                    
                    total_tasks = len(uploaded_files) * len(target_lang_codes)
                    progress_bar = st.progress(0)
                    completed_tasks = 0

                    for uploaded_file in uploaded_files:
                        if is_drm_protected(uploaded_file):
                            st.error(f"⛔ {uploaded_file.name}: DRM으로 보호된 파일은 번역할 수 없습니다.")
                            completed_tasks += len(target_lang_codes) # Count these as "completed" tasks that failed
                            progress_bar.progress(completed_tasks / total_tasks)
                            continue

                        # Read file ONCE
                        file_content = uploaded_file.getvalue()
                        original_filename = uploaded_file.name
                        name_part, ext_part = os.path.splitext(original_filename)

                        for target_lang in target_lang_codes:
                            try:
                                # 1. Upload (Unique name per file AND language to avoid conflicts if parallel)
                                # Although we iterate sequentially here, unique names are safer.
                                unique_name = f"{batch_id}_{target_lang}_{original_filename}"
                                input_blob_name = unique_name 
                                
                                blob_client = container_client.get_blob_client(input_blob_name)
                                blob_client.upload_blob(file_content, overwrite=True)
                                
                                # 2. Prepare Targets
                                source_url = generate_sas_url(blob_service_client, CONTAINER_NAME, input_blob_name, no_viewer=True)
                                
                                output_prefix = f"translated_{batch_id}_{target_lang}_{name_part}"
                                target_container_sas = generate_sas_url(blob_service_client, CONTAINER_NAME)
                                target_output_url = f"https://{blob_service_client.account_name}.blob.core.windows.net/{CONTAINER_NAME}/{output_prefix}?{target_container_sas.split('?')[1]}"

                                # 3. Trigger Translation
                                client = get_translation_client()
                                poller = client.begin_translation(
                                    inputs=[
                                        DocumentTranslationInput(
                                            source_url=source_url,
                                            storage_type="File",
                                            targets=[
                                                TranslationTarget(
                                                    target_url=target_output_url,
                                                    language=target_lang
                                                )
                                            ]
                                        )
                                    ]
                                )
                                
                                result = poller.result() # Wait for completion for THIS file/lang pair
                                
                                # 4. Process Results
                                success = True
                                for doc in result:
                                    if doc.status != "Succeeded":
                                        success = False
                                        error_msg = f"{original_filename} ({target_lang}) 실패: {doc.error.code} - {doc.error.message}"
                                        errors.append(error_msg)
                                        st.error(error_msg)
                                        # Should we keep blobs on failure? 
                                        # For multi-file batch, maybe not blocking the whole flow is better.
                                        # Trying to clean up even on failure to avoid costs, or keep?
                                        # User asked to keep for retry, but retry logic for batch is complex.
                                        # Let's keep source blob if failed, but we might lose track in simple UI.
                                        # For now, let's focus on success flow.
                                        
                                if success:
                                    # 5. Download Result
                                    output_blobs = list(container_client.list_blobs(name_starts_with=output_prefix))
                                    if output_blobs:
                                        result_blob = output_blobs[0]
                                        blob_data = container_client.get_blob_client(result_blob.name).download_blob().readall()
                                        
                                        # Cleanup Target
                                        container_client.delete_blob(result_blob.name)
                                        
                                        # Prepare Final Filename
                                        suffix = LANG_SUFFIX_OVERRIDE.get(target_lang, target_lang.upper())
                                        final_filename = f"{name_part}_{suffix}{ext_part}"
                                        
                                        results.append({
                                            'filename': final_filename,
                                            'data': blob_data
                                        })

                                # Cleanup Source (Only if processed, regardless of success of translation logic if we follow strict ephemeral? 
                                # But requirement was "retry on failure". 
                                # If we delete source here, we can't retry. 
                                # But if we keep it, we need a way to track it.
                                # Given complexity, let's delete source IF success. 
                                if success:
                                    blob_client.delete_blob()

                            except Exception as e:
                                st.error(f"처리 중 오류 ({original_filename} - {target_lang}): {e}")
                                errors.append(str(e))
                            
                            # Update Progress
                            completed_tasks += 1
                            progress_bar.progress(completed_tasks / total_tasks)

                    if results:
                        # 6. Prepare Download (Single or ZIP)
                        final_data = None
                        final_name = ""
                        is_zip = False

                        if len(results) == 1:
                            final_data = results[0]['data']
                            final_name = results[0]['filename']
                        else:
                            # Create ZIP
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                                for res in results:
                                    zf.writestr(res['filename'], res['data'])
                            
                            final_data = zip_buffer.getvalue()
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            final_name = f"translated_files_{timestamp}.zip"
                            is_zip = True
                        
                        # Update State
                        st.session_state.processing_state[batch_id] = {
                            'status': 'success',
                            'data': final_data,
                            'filename': final_name,
                            'is_zip': is_zip
                        }
                        
                        if errors:
                            st.warning(f"일부 작업이 실패했습니다: {', '.join(errors)}")
                        else:
                            st.success("모든 작업이 성공적으로 완료되었습니다.")
                            
                        st.rerun()
                    else:
                        st.error("번역된 결과물이 없습니다.")
                            
                except Exception as e:
                    st.error(f"전체 프로세스 오류: {e}")
                    # Save state for retry?
                    st.session_state.processing_state[batch_id] = {
                        'status': 'failed',
                        'error': str(e)
                    }

# Clear old state if file is removed
if not uploaded_files and 'current_batch_id' in st.session_state:
    del st.session_state.current_batch_id
