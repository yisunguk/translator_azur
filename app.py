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
            
    target_lang_label = st.selectbox("목표 언어 선택", lang_labels, index=default_index)
    target_lang_code = LANGUAGES[target_lang_label]
    st.info(f"선택된 목표 언어: {target_lang_code}")
    
    st.divider()



# -----------------------------
# Main Content
# -----------------------------
st.title("번역하기")

if "translate_uploader_key" not in st.session_state:
    st.session_state.translate_uploader_key = 0

uploaded_file = st.file_uploader("번역할 문서 업로드 (PPTX, PDF, DOCX, XLSX 등)", type=["pptx", "pdf", "docx", "xlsx"], key=f"translate_{st.session_state.translate_uploader_key}")

if uploaded_file:
    if is_drm_protected(uploaded_file):
        st.error("⛔ DRM으로 보호된 파일(암호화된 파일)은 번역할 수 없습니다.")
    else:
        # Generate a unique key for this file upload session if not exists
        if 'current_file_id' not in st.session_state:
            st.session_state.current_file_id = str(uuid.uuid4())
            
        col1, col2 = st.columns([1, 1])
        with col1:
             start_btn = st.button("번역 시작", type="primary", use_container_width=True)
        
        # Retry Logic
        retry_info = st.session_state.processing_state.get(st.session_state.current_file_id)
        if retry_info and retry_info.get('status') == 'failed':
            with col2:
                if st.button("🔄 재시도", use_container_width=True):
                    start_btn = True # Trigger start logic


        # 5. Result Display Logic (Persistent)
        current_state = st.session_state.processing_state.get(file_id)
        if current_state and current_state.get('status') == 'success':
            st.success("번역 완료! (임시 파일 삭제됨)")
            st.download_button(
                label=f"📥 {current_state['filename']} 다운로드",
                data=current_state['data'],
                file_name=current_state['filename'],
                mime="application/octet-stream",
                type="primary"
            )

        if start_btn:
            # Clear previous success state if re-running
            if current_state and current_state.get('status') == 'success':
                 del st.session_state.processing_state[file_id]
            
            with st.spinner("파일 처리 및 번역 중..."):
                try:
                    blob_service_client = get_blob_service_client()
                    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
                    
                    # Ensure container exists
                    if not container_client.exists():
                        container_client.create_container()

                    # 1. Upload (or reuse existing blob if retrying)
                    original_filename = uploaded_file.name
                    unique_name = f"{file_id}_{original_filename}"
                    input_blob_name = unique_name # Upload to Root
                    
                    # Check if already exists (for retry) or upload
                    blob_client = container_client.get_blob_client(input_blob_name)
                    if not blob_client.exists():
                        blob_client.upload_blob(uploaded_file, overwrite=True)
                    
                    # 2. Prepare Targets
                    source_url = generate_sas_url(blob_service_client, CONTAINER_NAME, input_blob_name, no_viewer=True)
                    
                    # Use a virtual directory for output to avoid name collision with source if in same container
                    # We will delete this immediately after success
                    output_prefix = f"translated_{file_id}" 
                    target_container_sas = generate_sas_url(blob_service_client, CONTAINER_NAME) # Container SAS
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
                                        language=target_lang_code
                                    )
                                ]
                            )
                        ]
                    )
                    
                    result = poller.result() # Wait for completion
                    
                    # 4. Process Results
                    success = True
                    for doc in result:
                        if doc.status != "Succeeded":
                            success = False
                            error_msg = f"에러: {doc.error.code} - {doc.error.message}" if doc.error else "Unknown Error"
                            st.session_state.processing_state[file_id] = {
                                'status': 'failed',
                                'source_blob': input_blob_name,
                                'target_prefix': output_prefix, # Keep for potential cleanup later
                                'error': error_msg
                            }
                            st.error(f"번역 실패: {error_msg}")
                            
                    if success:
                        # 5. Download Result to Memory
                        # The file will be at {output_prefix}/{unique_name} (usually)
                        # We need to find the file in the output prefix
                        output_blobs = list(container_client.list_blobs(name_starts_with=output_prefix))
                        if not output_blobs:
                            st.error("번역은 성공했으나 결과 파일을 찾을 수 없습니다.")
                        else:
                            result_blob = output_blobs[0] # Assume single file
                            blob_data = container_client.get_blob_client(result_blob.name).download_blob().readall()
                            
                            # 6. Cleanup (Delete Blobs)
                            # Delete Source
                            blob_client.delete_blob()
                            # Delete Target(s)
                            for b in output_blobs:
                                container_client.delete_blob(b.name)
                                
                            # 7. Provide Download
                            st.success("번역 완료! (임시 파일 삭제됨)")
                            
                            # Prepare filename
                            name_part, ext_part = os.path.splitext(original_filename)
                            suffix = LANG_SUFFIX_OVERRIDE.get(target_lang_code, target_lang_code.upper())
                            final_filename = f"{name_part}_{suffix}{ext_part}"
                            
                            # Update state with data for persistence
                            st.session_state.processing_state[file_id] = {
                                'status': 'success',
                                'data': blob_data,
                                'filename': final_filename
                            }
                            st.rerun() # Rerun to show the download button using the persistent block above
                            
                except Exception as e:
                    st.error(f"오류 발생: {e}")
                    # Save state for retry
                    st.session_state.processing_state[file_id] = {
                        'status': 'failed',
                        'error': str(e)
                    }

# Clear old state if file is removed
if not uploaded_file and 'current_file_id' in st.session_state:
    del st.session_state.current_file_id
