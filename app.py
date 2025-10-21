import streamlit as st
import edge_tts
import asyncio
import os
import uuid
import re
import json
import streamlit.components.v1 as components
from streamlit_lottie import st_lottie
import docx
import mammoth
import markdown
import PyPDF2
from striprtf.striprtf import rtf_to_text
from langdetect import detect, LangDetectException
import base64
import nest_asyncio
from pydub import AudioSegment
import aiohttp  
import ssl
import certifi

ssl._create_default_https_context = ssl._create_unverified_context  # Temporary workaround (not recommended for production)

# Apply nest_asyncio to allow nested event loops
nest_asyncio.apply()

# Utility Functions
def load_json(file, default):
    if os.path.exists(file):
        try:
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Failed to load {file}: {e}")
            return default
    return default

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Failed to save {file}: {e}")

def load_lottie(filepath):
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Failed to load animation: {e}")
        return None

# Streamlit Page Configuration
st.set_page_config(
    page_title="Text to Speech with Edge-TTS", layout="centered", page_icon="🗣️"
)
st.title("🗣️ Text-to-Speech App with Edge-TTS")

# Load and display Lottie animation
lottie_animation = load_lottie("assets/animation.json")
if lottie_animation:
    st_lottie(lottie_animation, height=150, key="header_animation")

# Custom CSS for styling
st.markdown(
    """
    <style>
    .main {
        background-color: #f9f9f9;
    }
    h1 {
        color: #3c3c3c;
        font-family: 'Segoe UI', sans-serif;
    }
    .stButton>button {
        background-color: #3b82f6;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        height: 3em;
        width: 100%;
    }
    .audio-controls button {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 5px 15px;
        margin: 0 5px;
        cursor: pointer;
    }
    .sentence:hover {
        background-color: #f0f0f0;
    }
    </style>
""",
    unsafe_allow_html=True,
)

# Voice and Speed Options
voice_options = {
    "DavisNeural - Male": "en-US-DavisNeural",
    "MohanNeural - Male": "te-IN-MohanNeural",
    "ShrutiNeural - Female": "te-IN-ShrutiNeural",
    "AriaNeural - Female": "en-US-AriaNeural",
    "SapnaNeural - Female": "kn-IN-SapnaNeural",
    "GaganNeural - Male": "kn-IN-GaganNeural",
}

speed_map = {"Fast": "+25%", "Normal": "+0%", "Slow": "-25%"}
rate_map = {"Fast": 1.25, "Normal": 1.0, "Slow": 0.75}

# Sidebar Settings
st.sidebar.header("🔧 Settings")
voice = st.sidebar.selectbox("Select Voice", list(voice_options.keys()))
# Default index = 1 → "Normal" (assuming keys are ["Fast","Normal","Slow"])
rate = st.sidebar.selectbox(
    "Select Speed", list(speed_map.keys()), index=list(speed_map.keys()).index("Normal")
)
# Browser voice options (for local browser-based playback if used)
browser_voice_options = {
    "English": "Microsoft Mark - English (United States)",
    "Kannada": "Microsoft Kannada Voice",
    "Telugu": "Microsoft Telugu Voice"
}
default_browser_voice = browser_voice_options.get("English" if voice.startswith("English") else "Telugu", "")
browser_voice = st.sidebar.text_input("Browser Voice Name (for Read Aloud)", value=default_browser_voice)

# Pronunciation Editor
PRON_FILE = "pronunciations.json"
pronunciations = load_json(PRON_FILE, {})

st.sidebar.subheader("🗣️ Pronunciation Editor (Persistent)")
custom_word = st.sidebar.text_input("Word (e.g., OpenAI)")
custom_pronunciation = st.sidebar.text_input("Pronunciation/SSML")

if st.sidebar.button("💾 Save Pronunciation"):
    if custom_word and custom_pronunciation:
        pronunciations[custom_word] = custom_pronunciation
        save_json(PRON_FILE, pronunciations)
        st.sidebar.success(f"Saved pronunciation for '{custom_word}'")

if pronunciations:
    st.sidebar.markdown("### 📌 Stored Pronunciations")
    for word, pron in pronunciations.items():
        st.sidebar.write(f"- **{word}** → {pron}")

# File Text Extraction
def extract_text_from_file(uploaded_file, file_type):
    try:
        if file_type == "txt":
            return uploaded_file.read().decode("utf-8")
        elif file_type == "pdf":
            reader = PyPDF2.PdfReader(uploaded_file)
            return "\n".join(
                page.extract_text() for page in reader.pages if page.extract_text()
            )
        elif file_type == "docx":
            document_obj = docx.Document(uploaded_file)
            return "\n".join([para.text for para in document_obj.paragraphs])
        elif personally_type == "doc":
            result = mammoth.convert_to_markdown(uploaded_file)
            return result.value
        elif file_type == "md":
            raw_md = uploaded_file.read().decode("utf-8")
            return markdown.markdown(raw_md)
        elif file_type == "rtf":
            raw_rtf = uploaded_file.read().decode("utf-8")
            return rtf_to_text(raw_rtf)
        return ""
    except Exception as e:
        st.error(f"Error processing file: {e}")
        return ""

# History Management
HISTORY_FILE = "history.json"
history = load_json(HISTORY_FILE, [])

st.sidebar.subheader("📝 History of Texts")
if history:
    selected_history = st.sidebar.selectbox(
        "Pick a saved text", ["Select a text..."] + history
    )
    if (
        selected_history != "Select a text..."
        and st.sidebar.button("🔄 Load from History")
    ):
        st.session_state["loaded_text"] = selected_history
        st.sidebar.success("Loaded from history!")

    # Clear History Button
    if st.sidebar.button("🗑️ Clear History"):
        history.clear()
        save_json(HISTORY_FILE, [])
        st.session_state.pop("loaded_text", None)
        st.sidebar.success("History cleared!")
else:
    st.sidebar.write("No history available.")

# Clear Loaded Text Button
if "loaded_text" in st.session_state and st.sidebar.button("🧹 Clear Loaded Text"):
    st.session_state.pop("loaded_text", None)
    st.sidebar.success("Loaded text cleared!")

# Input Handling
input_mode = st.radio("Choose Input Type", ["Type Text", "Upload File"])
user_text = ""

if input_mode == "Type Text":
    user_text = st.text_area("Enter Text to Convert to Speech", height=200)
else:
    uploaded_file = st.file_uploader(
        "Upload a text file", type=["txt", "pdf", "doc", "docx", "md", "json", "rtf"]
    )
    if uploaded_file is not None:
        file_type = uploaded_file.name.split(".")[-1].lower()
        user_text = extract_text_from_file(uploaded_file, file_type)

# Load from session state if available
if "loaded_text" in st.session_state and st.session_state["loaded_text"]:
    user_text = st.session_state["loaded_text"]

# Save to history
if user_text and st.button("📌 Save to History"):
    if user_text not in history:
        history.append(user_text)
        save_json(HISTORY_FILE, history)
        st.success("✅ Text saved to history")

# Language Detection and Voice Validation
def validate_language_and_voice(text, selected_voice):
    try:
        lang = detect(text)
        st.sidebar.markdown(f"🌍 Detected Language: **{lang.upper()}**")
        if lang == "te" and not selected_voice.startswith("Telugu"):
            st.warning("⚠️ Telugu text detected. Consider selecting a Telugu voice.")
        elif lang == "en" and not selected_voice.startswith("English"):
            st.warning("⚠️ English text detected. Consider selecting an English voice.")
        return lang
    except LangDetectException:
        st.sidebar.warning("⚠️ Could not detect language")
        return None

# Apply pronunciations once
def apply_pronunciations(text, pronunciations):
    for word, pron in pronunciations.items():
        text = text.replace(word, pron)
    return text

def clean_text(text):
    # Keep letters, numbers, spaces, basic punctuation, and specific symbols (-, +)
    # Remove #, *, and other unwanted symbols
    text = re.sub(r'[#*]', '', text)
    return text

# Async TTS Generation for a single chunk
async def generate_speech_chunk(text, voice, rate, output_file, retries=3):
    for attempt in range(retries):
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
            await communicate.save(output_file)
            return True
        except Exception as e:
            if attempt < retries - 1:
                await asyncio.sleep(3)
                st.warning(f"⚠️ Retrying chunk ({attempt+1}/{retries}) due to: {e}")
            else:
                st.error(f"❌ Failed to generate audio chunk: {e}")
                st.code(f"Voice: {voice}\nRate: {rate}\nText: {text[:200]}")
                return False

# Helper function to run async code safely in Streamlit
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Split text into chunks (e.g., by sentences, aiming for ~5000 chars per chunk to avoid limits)
def split_text_into_chunks(text, max_chars=5000):
    chunks = []
    current_chunk = ""
    sentences = re.split(r'(?<=[.!?]) +', text)
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += " " + sentence
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

# Process and generate speech
if user_text:
    # Validate language
    validate_language_and_voice(user_text, voice)
    
    # Apply pronunciations
    processed_text = apply_pronunciations(user_text, pronunciations)
    cleaned_text = clean_text(processed_text)

    if st.button("🎧 Convert to Speech"):
        output_file = f"{uuid.uuid4().hex}.mp3"
        temp_files = []
        try:
            with st.spinner("Generating audio... Please wait ⏳"):
                chunks = split_text_into_chunks(cleaned_text)
                for i, chunk in enumerate(chunks):
                    temp_file = f"temp_{i}_{uuid.uuid4().hex}.mp3"
                    success = run_async(
                        generate_speech_chunk(chunk, voice_options[voice], speed_map[rate], temp_file)
                    )
                    if success:
                        temp_files.append(temp_file)
                    else:
                        raise Exception("Failed to generate one or more audio chunks")

                # Concatenate all temp files
                if temp_files:
                    combined = AudioSegment.empty()
                    for temp in temp_files:
                        combined += AudioSegment.from_mp3(temp)
                    combined.export(output_file, format="mp3")

            if os.path.exists(output_file):
                st.success("✅ Conversion Complete!")
                try:
                    with open(output_file, "rb") as audio_file:
                        audio_bytes = audio_file.read()
                        audio_base64 = base64.b64encode(audio_bytes).decode()
                        st.markdown(
                            f"""
                            <audio id="tts-audio" controls style="width:100%;">
                                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
                                Your browser does not support the audio element.
                            </audio>
                            <div class="audio-controls" style="margin-top:8px;">
                                <button onclick="var a=document.getElementById('tts-audio'); if (!isNaN(a.currentTime)) a.currentTime=Math.max(0,a.currentTime-10);">⏪ 10s</button>
                                <button onclick="var a=document.getElementById('tts-audio'); if (!isNaN(a.currentTime) && !isNaN(a.duration)) a.currentTime=Math.min(a.duration,a.currentTime+10);">10s ⏩</button>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.download_button(
                            label="📥 Download Audio",
                            data=audio_bytes,
                            file_name="converted_speech.mp3",
                            mime="audio/mp3",
                        )
                except Exception as e:
                    st.error(f"Error reading audio file: {e}")
        finally:
            # Clean up temp files
            for temp in temp_files:
                if os.path.exists(temp):
                    try:
                        os.remove(temp)
                    except Exception as e:
                        st.warning(f"Failed to clean up temp file: {e}")
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                except Exception as e:
                    st.warning(f"Failed to clean up audio file: {e}")

# Browser-based TTS
if user_text and st.button("🗣️ Read Aloud in Browser"):
    cleaned_text = clean_text(user_text)
    escaped_text = cleaned_text.replace('"', '\\"').replace("\n", " ")
    # Use the selected browser voice
    html_code = f"""
    <script>
    let utterance = null;
    let wordIndex = 0;
    let words = [];
    let spans = [];
    let paused = false;
    let text = `{escaped_text}`;
    function speakText() {{
        utterance = new SpeechSynthesisUtterance(text);
        let allVoices = speechSynthesis.getVoices();
        const preferredVoiceName = "{browser_voice}";
        const matchedVoice = preferredVoiceName ? allVoices.find(v => v.name === preferredVoiceName) : allVoices[0];
        if (matchedVoice) utterance.voice = matchedVoice;
        utterance.rate = {rate_map[rate]};

        const container = document.getElementById("highlighted-text");
        words = text.split(/\\s+/);
        container.innerHTML = words.map(w => `<span class='word'>${{w}}</span>`).join(" ");
        spans = container.querySelectorAll(".word");
        wordIndex = 0;

        utterance.onboundary = (event) => {{
            if (event.name === 'word') {{
                spans.forEach(span => span.style.background = '');
                if (spans[wordIndex]) {{
                    spans[wordIndex].style.background = 'yellow';
                    wordIndex++;
                }}
            }}
        }};

        utterance.onend = () => {{
            spans.forEach(span => span.style.background = '');
            wordIndex = 0;
        }};

        speechSynthesis.speak(utterance);
    }}

    function skip10s(forward) {{
        if (!utterance) return;
        speechSynthesis.pause();
        if (forward) {{
            wordIndex = Math.min(words.length-1, wordIndex+20);
        }} else {{
            wordIndex = Math.max(0, wordIndex-20);
        }}
        speechSynthesis.cancel();
        let newText = words.slice(wordIndex).join(' ');
        utterance = new SpeechSynthesisUtterance(newText);
        let allVoices = speechSynthesis.getVoices();
        const preferredVoiceName = "{browser_voice}";
        const matchedVoice = preferredVoiceName ? allVoices.find(v => v.name === preferredVoiceName) : allVoices[0];
        if (matchedVoice) utterance.voice = matchedVoice;
        utterance.rate = {rate_map[rate]};
        utterance.onboundary = (event) => {{
            if (event.name === 'word') {{
                spans.forEach(span => span.style.background = '');
                if (spans[wordIndex]) {{
                    spans[wordIndex].style.background = 'yellow';
                    wordIndex++;
                }}
            }}
        }};
        utterance.onend = () => {{
            spans.forEach(span => span.style.background = '');
            wordIndex = 0;
        }};

        speechSynthesis.speak(utterance);
    }}

    function togglePauseResume() {{
        if (!window.speechSynthesis || !utterance) return;
        if (speechSynthesis.speaking && !speechSynthesis.paused) {{
            speechSynthesis.pause();
        }} else if (speechSynthesis.paused) {{
            speechSynthesis.resume();
        }}
    }}

    window.onload = function() {{
        speechSynthesis.onvoiceschanged = () => speakText();
    }};
    </script>
    <style>
    #highlighted-text {{ font-size: 18px; line-height: 1.6; margin-top: 10px; }}
    .word {{ padding: 2px; margin-right: 2px; }}
    </style>
    <div id="highlighted-text"></div>
    <div class="audio-controls" style="margin-top:8px;">
        <button onclick="skip10s(false)">⏪ 10s</button>
        <button onclick="togglePauseResume()">⏯️ Pause/Resume</button>
        <button onclick="skip10s(true)">10s ⏩</button>
    </div>
    """
    components.html(html_code)

# Sentence-by-Sentence Reading
if user_text:
    cleaned_text = clean_text(user_text)
    escaped_sentences = re.split(r"(?<=[.!?]) +", cleaned_text.replace("\n", " "))
    js_sentence_click = """
    <div id="sentence-text" style="line-height: 2; padding: 10px; max-height: 300px; overflow-y: auto;">
    """
    for sentence in escaped_sentences:
        clean_sent = sentence.strip().replace('"', '\\"')
        js_sentence_click += (
            f"<span class='sentence' onclick='speakSentence(\"{clean_sent}\")' style='cursor:pointer; display:block; padding:5px; margin-bottom:8px; border:1px solid #ccc; border-radius:6px;'>"
            + sentence
            + "</span>"
        )
    js_sentence_click += "</div>"

    actual_voice_name = voice_options[voice]
    js_sentence_click += f"""
<script>
let synth = window.speechSynthesis;
let sentenceUtterance = null;
let voicesLoaded = false;
let cachedVoices = [];

function loadVoices() {{
    return new Promise(resolve => {{
        let voices = synth.getVoices();
        if (voices.length !== 0) {{
            voicesLoaded = true;
            cachedVoices = voices;
            resolve(voices);
        }} else {{
            synth.onvoiceschanged = () => {{
                voicesLoaded = true;
                cachedVoices = synth.getVoices();
                resolve(cachedVoices);
            }};
        }}
    }});
}}

function speakSentence(sentence) {{
    if (!voicesLoaded) {{
        loadVoices().then(() => speakSentence(sentence));
        return;
    }}

    synth.cancel();

    let allSpans = Array.from(document.querySelectorAll('.sentence'));
    let startIndex = allSpans.findIndex(el => el.textContent.trim() === sentence.trim());
    if (startIndex === -1) return;

    let remainingSentences = allSpans.slice(startIndex).map(el => el.textContent).join(' ');
    sentenceUtterance = new SpeechSynthesisUtterance(remainingSentences);

    const preferredVoiceName = "{browser_voice}";
    const matched = cachedVoices.find(v => v.name === preferredVoiceName) || cachedVoices[0];
    sentenceUtterance.voice = matched;
    sentenceUtterance.lang = matched.lang;
    sentenceUtterance.rate = {rate_map[rate]};

    allSpans.forEach(el => el.style.background = '');
    if (allSpans[startIndex]) {{
        allSpans[startIndex].style.background = 'yellow';
        allSpans[startIndex].scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }}

    sentenceUtterance.onend = () => {{
        allSpans.forEach(el => el.style.background = '');
        sentenceUtterance = null;
    }};

    synth.speak(sentenceUtterance);
}}

function togglePauseResume() {{
    if (!window.speechSynthesis || !sentenceUtterance) return;
    if (synth.speaking && !synth.paused) {{
        synth.pause();
    }} else if (synth.paused) {{
        synth.resume();
    }}
}}

function skipSentence(forward) {{
    let sentences = Array.from(document.querySelectorAll('.sentence'));
    let current = sentences.findIndex(el => el.style.background === 'yellow');
    let next = forward ? Math.min(sentences.length-1, current+1) : Math.max(0, current-1);
    if (next !== -1 && next !== current) {{
        sentences[next].click();
    }}
}}

</script>

<div class="audio-controls" style="margin-top:1px;">
    <button onclick="skipSentence(false)">⏪ Prev</button>
    <button onclick="togglePauseResume()">⏯️ Pause/Resume</button>
    <button onclick="skipSentence(true)">Next ⏩</button>
</div>

<style>
.sentence:hover {{
    background-color: #f0f0f0;
}}
</style>
"""

    st.markdown("### 📌 Click a sentence to read it aloud")
    components.html(js_sentence_click, height=350)

st.markdown("---")
st.caption("🔊 Built with ❤️ by Sudarshan using Edge-TTS and Streamlit")

