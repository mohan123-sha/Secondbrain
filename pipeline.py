import os
import re
import sys
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

# Ensure we can import from the backend directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_collection

load_dotenv()

# Setup Local raw data directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DATA_DIR = os.path.join(BASE_DIR, "data", "raw")
os.makedirs(RAW_DATA_DIR, exist_ok=True)

# ----------------------------------------------------------------------
# 1. ZOOM CLOUD API INTEGRATION
# ----------------------------------------------------------------------

def get_zoom_access_token():
    """Retrieve Zoom Access Token using Server-to-Server OAuth."""
    account_id = os.getenv("ZOOM_ACCOUNT_ID")
    client_id = os.getenv("ZOOM_CLIENT_ID")
    client_secret = os.getenv("ZOOM_CLIENT_SECRET")
    
    if not all([account_id, client_id, client_secret]):
        print("[Zoom API] Warning: Zoom credentials not fully configured in backend/.env.")
        return None
        
    print("[Zoom API] Authenticating with Zoom using Server-to-Server OAuth...")
    url = "https://zoom.us/oauth/token"
    params = {
        "grant_type": "account_credentials",
        "account_id": account_id
    }
    
    try:
        # standard Basic Auth for Client ID & Secret
        auth = (client_id, client_secret)
        response = httpx.post(url, params=params, auth=auth, timeout=15.0)
        
        if response.status_code == 200:
            token_data = response.json()
            print("[Zoom API] Authentication successful!")
            return token_data.get("access_token")
        else:
            print(f"[Zoom API] Authentication failed (Status {response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"[Zoom API] Connection error: {e}")
        return None


def fetch_zoom_recordings(access_token):
    """Fetch cloud recordings from Zoom from the past 6 months, using monthly intervals."""
    if not access_token:
        return []
        
    print("[Zoom API] Fetching cloud recordings from the past 6 months...")
    url = "https://api.zoom.us/v2/users/me/recordings"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # Generate 6 non-overlapping 30-day blocks (since Zoom limits queries to 1-month range max)
    from datetime import timedelta
    today = datetime.now()
    intervals = []
    for i in range(6):
        end_date = today - timedelta(days=i * 30)
        start_date = today - timedelta(days=(i + 1) * 30)
        intervals.append((start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
        
    all_meetings = []
    seen_meeting_ids = set()
    
    try:
        for start, end in intervals:
            print(f"[Zoom API] Querying interval: {start} to {end}")
            params = {
                "from": start,
                "to": end,
                "page_size": 30,
                "trash": False
            }
            response = httpx.get(url, headers=headers, params=params, timeout=20.0)
            if response.status_code == 200:
                data = response.json()
                meetings = data.get("meetings", [])
                for m in meetings:
                    m_id = m.get("id")
                    if m_id not in seen_meeting_ids:
                        seen_meeting_ids.add(m_id)
                        all_meetings.append(m)
            else:
                # If a specific month fails (e.g. rate limit), continue to others
                print(f"[Zoom API] Interval failed (Status {response.status_code})")
                
        print(f"[Zoom API] Found {len(all_meetings)} total cloud recordings in past 6 months.")
        return all_meetings
    except Exception as e:
        print(f"[Zoom API] Error fetching recordings: {e}")
        return []


def filter_and_download_zoom_files(meetings, access_token):
    """
    Retrieves the last 5 cloud recordings across the entire account
    and downloads their transcript/summary files.
    """
    if not meetings:
        return []
        
    # Sort by start_time descending to get the most recent meetings
    meetings.sort(key=lambda x: x.get("start_time", ""), reverse=True)
    
    # Take the last 5
    recent_5 = meetings[:5]
    print(f"[Zoom API] Processing the {len(recent_5)} most recent recordings in the account.")
    
    downloaded_files = []
    
    for meeting in recent_5:
        meeting_id = meeting.get("id")
        topic = meeting.get("topic", "Zoom Meeting")
        start_time_str = meeting.get("start_time") # Example: 2026-05-25T10:00:00Z
        
        # Parse start_time to clean date/time format for filename
        try:
            dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            try:
                dt = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%S%z")
            except Exception:
                dt = datetime.now()
                
        formatted_date = dt.strftime("%Y-%m-%d_%H-%M")
        
        recording_files = meeting.get("recording_files", [])
        print(f"[Zoom API] Meeting '{topic}' on {formatted_date} has {len(recording_files)} files.")
        
        for file in recording_files:
            file_type = file.get("file_type", "")
            download_url = file.get("download_url", "")
            
            file_ext = file.get("file_extension", "").lower()
            
            is_text_file = (
                file_type in ["TRANSCRIPT", "SUMMARY", "CHAT"] or 
                (file_ext in ["vtt", "txt", "docx", "json"] and file_type != "TIMELINE")
            )

            
            if is_text_file and download_url:
                ext = file_ext if file_ext else ("vtt" if file_type == "TRANSCRIPT" else "txt")
                
                # Standardize the topic name for filenames: strip special characters, replace spaces/hyphens with underscores
                clean_topic = re.sub(r"[^a-zA-Z0-9_\s\-]", "", topic)
                clean_topic = re.sub(r"[\s\-]+", "_", clean_topic).strip("_")
                
                filename = f"{clean_topic}_{formatted_date}.{ext}"
                local_path = os.path.join(RAW_DATA_DIR, filename)
                
                print(f"[Zoom API] Downloading {file_type} to {filename}...")
                
                # To download Zoom recordings, append access_token to the download url
                auth_download_url = f"{download_url}?access_token={access_token}"
                
                try:
                    res = httpx.get(auth_download_url, follow_redirects=True, timeout=30.0)
                    if res.status_code == 200:

                        with open(local_path, "wb") as f:
                            f.write(res.content)
                        print(f"[Zoom API] Downloaded successfully!")
                        downloaded_files.append({
                            "path": local_path,
                            "name": filename,
                            "meeting_date": dt.strftime("%Y-%m-%d"),
                            "topic": topic
                        })
                    else:
                        print(f"[Zoom API] Failed to download file (Status {res.status_code})")
                except Exception as e:
                    print(f"[Zoom API] Error downloading file: {e}")
                    
    return downloaded_files


# ----------------------------------------------------------------------
# 2. BOX API STORAGE INTEGRATION
# ----------------------------------------------------------------------

def upload_files_to_box(downloaded_files):
    """
    Uploads downloaded meeting files to the specific Box folder "Esperia SecondBrain".
    Using the standard Box SDK with Client Credentials Grant (CCG) Auth from config.json.
    Automatically refreshes tokens indefinitely!
    """
    print("[Box API] Authenticating with Box...")
    client = None
    
    # 1. Dynamic Config File Search & S2S JWT/CCG Authentication
    config_files = [f for f in os.listdir(BASE_DIR) if f.endswith("config.json")]
    
    if config_files:
        config_filename = config_files[0]
        config_path = os.path.join(BASE_DIR, config_filename)
        print(f"[Box API] Found Box config file: {config_filename}. Loading credentials...")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                box_config = json.load(f)
                
            client_id = box_config["boxAppSettings"]["clientID"]
            client_secret = box_config["boxAppSettings"]["clientSecret"]
            enterprise_id = box_config.get("enterpriseID")
            
            # Check if appAuth has privateKey populated (for JWT authentication)
            app_auth = box_config["boxAppSettings"].get("appAuth", {})
            has_private_key = bool(app_auth.get("privateKey"))
            
            if has_private_key:
                # Initialize JWT authentication
                print("[Box API] Initializing Server-to-Server JWT Authentication...")
                from box_sdk_gen import BoxJWTAuth, BoxClient, JWTConfig
                jwt_config = JWTConfig.from_config_file(config_path)
                auth = BoxJWTAuth(jwt_config)
                client = BoxClient(auth)
                auth.retrieve_token() # Verify token retrieval
                print("[Box API] JWT Authentication successful! Token will be auto-refreshed.")
            else:
                # Initialize CCG authentication
                print("[Box API] Initializing Server-to-Server CCG Authentication...")
                from box_sdk_gen import BoxCCGAuth, BoxClient, CCGConfig
                auth_config = CCGConfig(
                    client_id=client_id,
                    client_secret=client_secret,
                    enterprise_id=enterprise_id
                )
                auth = BoxCCGAuth(auth_config)
                client = BoxClient(auth)
                auth.retrieve_token() # Verify token retrieval
                print("[Box API] CCG Authentication successful! Token will be auto-refreshed.")
        except Exception as e:
            print(f"[Box API] Config-file Authentication failed (verify admin authorization): {e}")
            client = None
            
    # 2. Fallback to Box Developer Token in .env if config-file auth fails
    if not client:
        developer_token = os.getenv("BOX_DEVELOPER_TOKEN")
        if developer_token:
            print("[Box API] Falling back to Box Developer Token auth...")
            try:
                from box_sdk_gen import BoxDeveloperTokenAuth, BoxClient
                auth = BoxDeveloperTokenAuth(developer_token)
                client = BoxClient(auth)
                print("[Box API] Developer Token Authentication successful.")
            except Exception as e:
                print(f"[Box API] Failed Developer Token Auth: {e}")
                client = None
                
    if not client:
        print("[Box API] Warning: No valid Box authentication found. Skipping Box upload (files saved locally).")
        return False
        
    target_folder_name = "Esperia SecondBrain"
    
    try:
        from box_sdk_gen.box.errors import BoxAPIError
        from box_sdk_gen import CreateFolderParent
        
        # Step 1: Find or Create the 'Esperia SecondBrain' folder in root (ID '0')
        items = client.folders.get_folder_items(folder_id='0')
        
        target_folder = None
        for item in items.entries:
            if item.type == 'folder' and item.name == target_folder_name:
                target_folder = item
                print(f"[Box API] Found existing Box folder '{target_folder_name}' with ID: {target_folder.id}")
                break
                
        if not target_folder:
            print(f"[Box API] Creating new folder '{target_folder_name}' in Box root...")
            target_folder = client.folders.create_folder(
                name=target_folder_name,
                parent=CreateFolderParent(id="0")
            )
            print(f"[Box API] Successfully created Box folder with ID: {target_folder.id}")
            
        # Step 2: Upload each downloaded file to the Box folder
        for file_info in downloaded_files:
            file_path = file_info["path"]
            filename = file_info["name"]
            
            print(f"[Box API] Uploading {filename} to Box...")
            try:
                from box_sdk_gen import UploadFileAttributes, UploadFileAttributesParentField
                parent_field = UploadFileAttributesParentField(id=target_folder.id)
                attributes = UploadFileAttributes(name=filename, parent=parent_field)
                with open(file_path, "rb") as f:
                    uploaded_file = client.uploads.upload_file(attributes=attributes, file=f)
                print(f"[Box API] Successfully uploaded '{filename}' to Box (File ID: {uploaded_file.entries[0].id})!")
            except BoxAPIError as box_err:
                if box_err.status_code == 409:
                    print(f"[Box API] File '{filename}' already exists in Box. Skipping upload.")
                else:
                    print(f"[Box API] Box SDK upload failed for '{filename}': {box_err.message}")
            except Exception as upload_err:
                print(f"[Box API] Upload error for '{filename}': {upload_err}")
                
        return True
        
    except Exception as e:
        print(f"[Box API] Error interacting with Box SDK: {e}")
        print("[Box API] Proceeding with locally cached files...")
        return False


# ----------------------------------------------------------------------
# 3. HIGH-QUALITY SEMANTIC / DIALOGUE-AWARE CHUNKING
# ----------------------------------------------------------------------

def clean_vtt_content(vtt_text):
    """
    Parses a raw WebVTT file, strips out headers, indexes, and timestamps,
    and returns a list of speaker dialogue blocks: [{"speaker": "John", "text": "..."}].
    """
    lines = vtt_text.splitlines()
    dialogue_blocks = []
    
    current_speaker = None
    current_speech = []
    
    # Regular expressions for VTT patterns
    timestamp_pattern = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}")
    
    for line in lines:
        line = line.strip()
        
        # Skip VTT meta headers & empty lines & timing lines
        if not line or line.startswith("WEBVTT") or line.startswith("NOTE") or timestamp_pattern.search(line) or line.isdigit():
            continue
            
        # Try to parse speaker format: "John: Hello everyone" or "<v John>Hello everyone</v>"
        # standard Zoom speaker formatting is usually "John: Hello"
        speaker_match = re.match(r"^([^:]+):\s*(.*)$", line)
        
        if speaker_match:
            # We hit a new speaker dialogue line
            speaker = speaker_match.group(1).strip()
            speech = speaker_match.group(2).strip()
            
            # Save the previous block if we had one
            if current_speaker:
                dialogue_blocks.append({
                    "speaker": current_speaker,
                    "text": " ".join(current_speech)
                })
                
            current_speaker = speaker
            current_speech = [speech]
        else:
            # If no speaker pattern, it's a continuation of the current speaker's text
            if current_speaker:
                current_speech.append(line)
            else:
                # If we have no speaker context yet (e.g. system notification or intro text)
                current_speaker = "Narrator"
                current_speech = [line]
                
    # Add final block
    if current_speaker and current_speech:
        dialogue_blocks.append({
            "speaker": current_speaker,
            "text": " ".join(current_speech)
        })
        
    return dialogue_blocks


def generate_high_quality_chunks(dialogue_blocks, meeting_name, meeting_date, target_char_len=700, overlap_len=150):
    """
    Groups dialogue blocks into cohesive semantic chunks with sliding overlaps.
    Prevents splitting speaker statements mid-sentence and prefixes context.
    """
    chunks = []
    current_chunk_blocks = []
    current_chunk_len = 0
    
    for block in dialogue_blocks:
        speaker = block["speaker"]
        text = block["text"]
        
        block_formatted = f"{speaker}: {text}"
        block_len = len(block_formatted)
        
        # If adding this speaker block makes the chunk too large, flush the current chunk
        if current_chunk_len + block_len > target_char_len and current_chunk_blocks:
            # Assemble chunk text
            chunk_body = "\n".join(current_chunk_blocks)
            # Prefix rich context headers (crucial RAG technique so chunks don't lose context)
            full_chunk_text = (
                f"[Meeting: {meeting_name} | Date: {meeting_date}]\n"
                f"----------------------------------------\n"
                f"{chunk_body}"
            )
            chunks.append(full_chunk_text)
            
            # Apply sliding window overlap by keeping the last 1-2 dialogue blocks
            # if they fit within overlap parameters
            overlap_blocks = []
            overlap_char_count = 0
            for prev_block in reversed(current_chunk_blocks):
                if overlap_char_count + len(prev_block) < overlap_len:
                    overlap_blocks.insert(0, prev_block)
                    overlap_char_count += len(prev_block)
                else:
                    break
                    
            current_chunk_blocks = overlap_blocks
            current_chunk_len = overlap_char_count
            
        current_chunk_blocks.append(block_formatted)
        current_chunk_len += block_len
        
    # Flush remaining blocks
    if current_chunk_blocks:
        chunk_body = "\n".join(current_chunk_blocks)
        full_chunk_text = (
            f"[Meeting: {meeting_name} | Date: {meeting_date}]\n"
            f"----------------------------------------\n"
            f"{chunk_body}"
        )
        chunks.append(full_chunk_text)
        
    return chunks


# ----------------------------------------------------------------------
# 4. CHROMADB VECTOR INDEXING
# ----------------------------------------------------------------------

def index_files_to_chroma(downloaded_files):
    """Reads the files, performs semantic chunking, and stores them in ChromaDB."""
    print("\n[ChromaDB Ingestion] Beginning vector indexing...")
    collection = get_collection()
    
    total_chunks_indexed = 0
    
    for file_info in downloaded_files:
        file_path = file_info["path"]
        filename = file_info["name"]
        meeting_date = file_info["meeting_date"]
        meeting_topic = file_info["topic"]
        
        print(f"[ChromaDB Ingestion] Processing {filename}...")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[ChromaDB Ingestion] Error reading file {filename}: {e}. Trying other encodings...")
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    content = f.read()
            except Exception as e2:
                print(f"[ChromaDB Ingestion] Failed completely: {e2}")
                continue
                
        # Parse dialogue depending on file format
        if filename.endswith(".vtt"):
            dialogue_blocks = clean_vtt_content(content)
        elif filename.endswith(".json"):
            try:
                json_data = json.loads(content)
                # 1. Skip timeline files containing "timeline"
                if "timeline" in json_data:
                    print(f"[ChromaDB Ingestion] Skipping Zoom timeline JSON file: {filename} (no actual dialogue text).")
                    continue
                
                # 2. Check for SUMMARY files containing "summary_details", "summary", or "markdown"
                dialogue_blocks = []
                
                if "summary_details" in json_data:
                    details = json_data["summary_details"]
                    if isinstance(details, list):
                        for detail in details:
                            lbl = detail.get("label", "Summary")
                            val = detail.get("value", "")
                            if val:
                                dialogue_blocks.append({
                                    "speaker": f"Zoom AI Companion ({lbl})",
                                    "text": val.strip()
                                })
                    elif isinstance(details, str) and details:
                        dialogue_blocks.append({
                            "speaker": "Zoom AI Companion (Details)",
                            "text": details.strip()
                        })
                        
                if "summary_overview" in json_data and json_data["summary_overview"]:
                    dialogue_blocks.append({
                        "speaker": "Zoom AI Companion (Overview)",
                        "text": json_data["summary_overview"].strip()
                    })
                    
                if "next_steps" in json_data and json_data["next_steps"]:
                    dialogue_blocks.append({
                        "speaker": "Zoom AI Companion (Next Steps)",
                        "text": json_data["next_steps"].strip()
                    })
                    
                if "markdown" in json_data and json_data["markdown"]:
                    dialogue_blocks.append({
                        "speaker": "Zoom AI Summary (Markdown)",
                        "text": json_data["markdown"].strip()
                    })
                    
                if "summary" in json_data:
                    sum_val = json_data["summary"]
                    if isinstance(sum_val, str) and sum_val:
                        dialogue_blocks.append({
                            "speaker": "Zoom AI Companion (Summary)",
                            "text": sum_val.strip()
                        })
                    elif isinstance(sum_val, dict):
                        for k, v in sum_val.items():
                            if isinstance(v, str) and v:
                                dialogue_blocks.append({
                                    "speaker": f"Zoom AI Companion ({k.capitalize()})",
                                    "text": v.strip()
                                })
                
                # Fallback if no specific keys found but we have some keys in JSON
                if not dialogue_blocks:
                    if isinstance(json_data, dict):
                        valid_keys = {k: v for k, v in json_data.items() if v and k not in ["code", "message", "status"]}
                        if not valid_keys or (len(valid_keys) == 1 and "total_items" in valid_keys):
                            print(f"[ChromaDB Ingestion] Skipping empty/trivial JSON file: {filename}")
                            continue
                        
                        summary_lines = []
                        for k, v in valid_keys.items():
                            if isinstance(v, str):
                                summary_lines.append(f"{k.capitalize()}: {v}")
                            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                                summary_lines.append(f"{k.capitalize()}:\n" + "\n".join(v))
                        if summary_lines:
                            dialogue_blocks.append({
                                "speaker": "Zoom Meeting Summary",
                                "text": "\n".join(summary_lines)
                            })
                            
                if not dialogue_blocks:
                    print(f"[ChromaDB Ingestion] Skipping JSON file {filename} (no queryable summary text found).")
                    continue
                    
            except json.JSONDecodeError as je:
                print(f"[ChromaDB Ingestion] JSON decode error in {filename}: {je}. Falling back to line parsing.")
                # Fallback to general line parser
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                dialogue_blocks = []
                for line in lines:
                    speaker_match = re.match(r"^([^:]+):\s*(.*)$", line)
                    if speaker_match:
                        dialogue_blocks.append({
                            "speaker": speaker_match.group(1).strip(),
                            "text": speaker_match.group(2).strip()
                        })
                    else:
                        dialogue_blocks.append({
                            "speaker": "Narrator/Summary",
                            "text": line
                        })
        else:
            # For standard text files, split by line and assume lines are dialogue
            # or split paragraphs if no speaker tags
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            dialogue_blocks = []
            for line in lines:
                speaker_match = re.match(r"^([^:]+):\s*(.*)$", line)
                if speaker_match:
                    dialogue_blocks.append({
                        "speaker": speaker_match.group(1).strip(),
                        "text": speaker_match.group(2).strip()
                    })
                else:
                    dialogue_blocks.append({
                        "speaker": "Narrator/Summary",
                        "text": line
                    })
                    
        if not dialogue_blocks:
            print(f"[ChromaDB Ingestion] Warning: No dialogue parsed from {filename}. Skipping.")
            continue
            
        print(f"[ChromaDB Ingestion] Parsed {len(dialogue_blocks)} dialogue utterances.")
        
        # Generate semantic chunks
        chunks = generate_high_quality_chunks(
            dialogue_blocks, 
            meeting_name=meeting_topic, 
            meeting_date=meeting_date
        )
        
        print(f"[ChromaDB Ingestion] Generated {len(chunks)} high-quality vector chunks.")
        
        # Prepare batches for ChromaDB
        documents = []
        metadatas = []
        ids = []
        
        for idx, chunk_text in enumerate(chunks):
            chunk_id = f"{filename}_chunk_{idx}"
            documents.append(chunk_text)
            metadatas.append({
                "source_file": filename,
                "meeting_name": meeting_topic,
                "meeting_date": meeting_date,
                "chunk_index": idx
            })
            ids.append(chunk_id)
            
        # Write to ChromaDB
        if documents:
            collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            total_chunks_indexed += len(documents)
            print(f"[ChromaDB Ingestion] Successfully upserted {len(documents)} chunks to ChromaDB.")
            
    print(f"[ChromaDB Ingestion] Completed! Total new chunks added: {total_chunks_indexed}. Collection now has {collection.count()} chunks.")


# ----------------------------------------------------------------------
# 5. MOCK DATA SEEDING (FALLBACK)
# ----------------------------------------------------------------------

def generate_mock_meetings_fallback():
    """
    Generates 5 highly realistic, detailed meeting transcripts 
    discussing onboarding, fundraising, hiring, and roadmap milestones
    to seed the system if APIs are not active.
    """
    print("\n[Pipeline Fallback] No cloud files downloaded. Seeding 5 highly realistic Esperia Weekly meetings...")
    
    mock_meetings = [
        {
            "date": "2026-05-25",
            "time": "10-00",
            "content": """WEBVTT

1
00:00:01.000 --> 00:00:06.000
Mohan: Good morning everyone! Let's kick off the Esperia Weekly Full-Team Meeting. 

2
00:00:06.100 --> 00:00:12.000
Mohan: First on the agenda is our fundraising. Alice, can you give us an update on the Seed round?

3
00:00:12.100 --> 00:00:22.000
Alice: Yes, Mohan! We have finalized terms with two institutional investors for our $2M Seed round. The lead investor is Sequoia India, and they are bringing in $1.2M. 

4
00:00:22.100 --> 00:00:30.000
Alice: The remaining $800k is split among angel investors. We expect to close the legal paperwork by next Friday, June 5th. 

5
00:00:30.100 --> 00:00:35.000
Mohan: Outstanding work, Alice! That's a huge milestone. What about the hiring pipeline?

6
00:00:35.100 --> 00:00:44.000
David: Hi everyone. Regarding hiring, we are actively looking for a Lead AI Engineer. I have interviewed three candidates last week. 

7
00:00:44.100 --> 00:00:52.000
David: Rajesh stood out with strong background in RAG pipelines and vector search. I recommend making him an offer today.

8
00:00:52.100 --> 00:00:57.000
Mohan: Agreed, Rajesh seemed phenomenal. Let's send out the offer letter by this evening.
"""
        },
        {
            "date": "2026-05-18",
            "time": "10-00",
            "content": """WEBVTT

1
00:00:01.000 --> 00:00:05.000
Mohan: Welcome to our Esperia Weekly Full-Team Meeting. Today is May 18th. 

2
00:00:05.100 --> 00:00:11.000
Mohan: Let's discuss our product roadmap. Shreya, what are the milestone timelines for MemoryOS?

3
00:00:11.100 --> 00:00:22.000
Shreya: Hi Mohan. The core engine of Esperia MemoryOS is 80% complete. We are on track to launch the Private Beta to our first 100 users on June 20th. 

4
00:00:22.100 --> 00:00:32.000
Shreya: The primary focus this week is connecting the local ChromaDB semantic memory indexing with the real-time background worker. 

5
00:00:32.100 --> 00:00:38.000
Mohan: Excellent. What about the user onboarding experience? We need a very smooth onboarding flow.

6
00:00:38.100 --> 00:00:48.000
Sarah: Yes, I have drafted the onboarding guidelines. The user will be greeted with an interactive wizard that explains how Esperia captures Zoom recordings. 

7
00:00:48.100 --> 00:00:55.000
Sarah: The wizard will take less than 2 minutes. I'll share the Figma wireframes in the Slack channel for feedback.
"""
        },
        {
            "date": "2026-05-11",
            "time": "10-00",
            "content": """WEBVTT

1
00:00:01.000 --> 00:00:05.000
Mohan: Let's start the Esperia Weekly Full-Team Meeting for May 11th. 

2
00:00:05.100 --> 00:00:10.000
Mohan: Today, we should review our data security and Box storage integration. 

3
00:00:10.100 --> 00:00:18.000
Karthik: Hi Mohan. I've successfully set up the Box API integration using Developer Tokens. 

4
00:00:18.100 --> 00:00:26.000
Karthik: All transcripts will be stored in a secure folder called 'Esperia SecondBrain'. We have enabled AES-256 encryption.

5
00:00:26.100 --> 00:00:32.000
Karthik: In terms of governance, only authorized users from Esperia will have read-write access to this folder.

6
00:00:32.100 --> 00:00:38.000
Mohan: That sounds highly secure. What is the plan for integrating the Zoom cloud transcripts?

7
00:00:38.100 --> 00:00:48.000
Karthik: We will write a Python script that polls the Zoom Cloud Recording API and automatically formats the file names to match meeting topic and date.
"""
        },
        {
            "date": "2026-05-04",
            "time": "10-00",
            "content": """WEBVTT

1
00:00:01.000 --> 00:00:06.000
Mohan: Good morning everyone, welcome to the Esperia Weekly Full-Team Meeting for May 4th.

2
00:00:06.100 --> 00:00:12.000
Mohan: Today we are aligning on our long-term vision. We are building the ultimate AI organizational memory engine.

3
00:00:12.100 --> 00:00:21.000
Mohan: In the future, a team member should be able to query Esperia and get instant synthesis of historical decisions.

4
00:00:21.100 --> 00:00:27.000
Shreya: Yes, this will eliminate hours of search time. Instead of reading transcripts, people just chat with Esperia.

5
00:00:27.100 --> 00:00:35.000
Shreya: We are starting with ChromaDB and sentence-transformers locally because it is fast, free, and completely secure for internal data.

6
00:00:35.100 --> 00:00:42.000
Mohan: Great. Let's make sure the chunking preserves dialogue context, otherwise the LLM answers will be out of sync.
"""
        },
        {
            "date": "2026-04-27",
            "time": "10-00",
            "content": """WEBVTT

1
00:00:01.000 --> 00:00:06.000
Mohan: Hello everyone, welcome to the Esperia Weekly Full-Team Meeting for April 27th.

2
00:00:06.100 --> 00:00:13.000
Mohan: First, let's align on our team structure. We need to hire a Technical Recruiter to handle the hiring pipeline.

3
00:00:13.100 --> 00:00:20.000
David: Yes Mohan, I've listed the job spec for the Recruiter role. We have already received 40 applications.

4
00:00:20.100 --> 00:00:28.000
David: I will filter the top 5 candidates by this Wednesday and schedule initial screening calls.

5
00:00:28.100 --> 00:00:33.000
Mohan: Super. That will free up our engineering team from heavy scheduling tasks.
"""
        }
    ]
    
    seeded_files = []
    
    for meeting in mock_meetings:
        filename = f"Esperia_Weekly_Full_Team_Meeting_{meeting['date']}_{meeting['time']}.vtt"
        local_path = os.path.join(RAW_DATA_DIR, filename)
        
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(meeting["content"])
            
        seeded_files.append({
            "path": local_path,
            "name": filename,
            "meeting_date": meeting["date"],
            "topic": "Esperia Weekly Full-Team Meeting"
        })
        
    print(f"[Pipeline Fallback] Seeded {len(seeded_files)} mock transcripts successfully!")
    return seeded_files


# ----------------------------------------------------------------------
# MAIN PIPELINE ENTRYPOINT
# ----------------------------------------------------------------------

def run_pipeline():
    print("======================================================================")
    print("      ESPERIA AI ORGANIZATIONAL MEMORY - INGESTION PIPELINE")
    print("======================================================================")
    
    downloaded_files = []
    
    # 1. Zoom API Ingestion
    zoom_token = get_zoom_access_token()
    if zoom_token:
        meetings = fetch_zoom_recordings(zoom_token)
        if meetings:
            downloaded_files = filter_and_download_zoom_files(meetings, zoom_token)
            
    # 2. Box Upload
    box_uploaded = False
    if downloaded_files:
        box_uploaded = upload_files_to_box(downloaded_files)
        
    # 3. Fallback Seeding
    if not downloaded_files:
        print("[Pipeline] No real Zoom transcripts could be downloaded.")
        downloaded_files = generate_mock_meetings_fallback()
        # Still try to upload mock files to Box if credentials exist
        upload_files_to_box(downloaded_files)
        
    # 4. High-Quality Chunking & ChromaDB Vector Indexing
    index_files_to_chroma(downloaded_files)
    
    print("\n======================================================================")
    print("      PIPELINE EXECUTION COMPLETE!")
    print("======================================================================")


if __name__ == "__main__":
    run_pipeline()
