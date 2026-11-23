"""
UI layer of the Wikipedia Article Extractor.
All scraping and formatting is done by wikipedia_extractor_core.py;
this file only shows widgets and keeps the user's progress in st.session_state.
"""
import streamlit as st
from wikipedia_extractor_core import WikipediaArticle, format_txt, numbered_filename

st.set_page_config(page_title="Wikipedia Extractor", layout="wide")


# ---------- session state ----------
# topic          : the topic the user searched for ("" if the box was empty)
# article        : the WikipediaArticle object (holds title, url, options, sections, error)
# selected       : section numbers that were extracted
# sections_data  : extracted sections, [{"title": ..., "blocks": [...]}, ...]
# text           : the .txt content from format_txt()
# downloaded_filenames : names already downloaded, so a repeat gets _2, _3 ...
DEFAULTS = {
    "topic": None,
    "article": None,
    "selected": [],
    "sections_data": [],
    "text": None,
    "downloaded_filenames": [],
}
for key in DEFAULTS:
    if key not in st.session_state:
        st.session_state[key] = DEFAULTS[key]

# Corrupt state guard: results without an article make no sense, so start that part again.
if st.session_state.article is None and (len(st.session_state.selected) > 0
                                         or len(st.session_state.sections_data) > 0
                                         or st.session_state.text is not None):
    for key in ["selected", "sections_data", "text", "downloaded_filenames"]:
        st.session_state[key] = DEFAULTS[key]
    st.rerun()

# Sections at the end of an article that hold no article text
NON_CONTENT = ["See also", "Notes", "References", "Citations", "Sources",
               "Bibliography", "Further reading", "External links"]


# ---------- callbacks (run before the page is redrawn) ----------
def reset_results():
    """Forget the sections chosen for the previous article."""
    st.session_state.selected = []
    st.session_state.sections_data = []
    st.session_state.text = None
    st.session_state.section_picker = []
    st.session_state.select_all = False


def search():
    """Fetch the article for the topic typed in the search form."""
    topic = st.session_state.topic_input.strip()
    st.session_state.topic = topic
    if topic == "":
        st.session_state.article = None
    else:
        st.session_state.article = WikipediaArticle(topic)
    reset_results()


def open_meaning():
    """Open the article the user picked on a disambiguation page."""
    st.session_state.article = WikipediaArticle(st.session_state.meaning)
    reset_results()


def extract():
    """Extract the chosen sections and build the .txt content."""
    article = st.session_state.article
    if st.session_state.select_all:
        chosen = [number for number, title, section in article.sections]
    else:
        chosen = sorted(st.session_state.section_picker)
    if len(chosen) == 0:              # nothing chosen: the page shows a warning instead
        return

    sections_data = []
    for number, title, section in article.sections:
        if number in chosen:
            sections_data.append(article.extract_section(title, section))

    st.session_state.selected = chosen
    st.session_state.sections_data = sections_data
    st.session_state.text = format_txt(article.title, article.url, sections_data)


def record_download(filename):
    """Remember a downloaded file name, so the next download gets a new number."""
    st.session_state.downloaded_filenames.append(filename)


# ---------- sidebar ----------
with st.sidebar:
    st.header("Wikipedia Extractor")
    st.caption("Clear everything and begin a new search.")
    if st.button("Start Over"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ---------- main area ----------
st.title("Wikipedia Article Extractor")

with st.expander("How to use this app"):
    st.markdown(
        "1. **Search** - enter a topic (e.g. Albert Einstein). "
        "If it has several meanings, choose one.\n"
        "2. **Select** - choose the sections you want, or tick *Select all sections*.\n"
        "3. **Extract** - click *Extract* and check the preview.\n"
        "4. **Download** - click *Download .txt* to save the file."
    )

article = st.session_state.article

# Count the sections that hold article text (not only references or links)
usable_count = 0
if article is not None and article.error is None:
    for number, title, section in article.sections:
        if title not in NON_CONTENT:
            usable_count += 1

# Progress indicator - each step is checked from the existing session state
steps = [
    ("Search", article is not None and article.error is None),
    ("Select", usable_count > 0),
    ("Extract", len(st.session_state.sections_data) > 0),
    ("Download", len(st.session_state.downloaded_filenames) > 0),
]
columns = st.columns(4)
for i in range(4):
    name, done = steps[i]
    mark = "✅" if done else "⬜"
    columns[i].caption(f"{mark} {i + 1}. {name}")

# 1) Search
with st.form("search_form"):
    st.text_input("Enter a topic", key="topic_input")
    st.form_submit_button("Search", on_click=search)

if st.session_state.topic == "":
    st.warning("Please type a topic.")

elif article is not None and article.error is not None:
    # 2) Error message (no article, network problem, no sections ...)
    st.error(article.error)

elif article is not None and len(article.options) > 0:
    # 3) Meaning choice - only for a disambiguation page (e.g. "Python")
    st.info(f"'{article.title}' has several meanings. Choose the article you want.")
    st.selectbox("Choose an article", article.options, key="meaning")
    st.button("Open article", on_click=open_meaning)

elif article is not None and usable_count == 0:
    # 2) Article found, but it has only reference or link sections
    st.subheader(article.title)
    st.markdown(f"Source: [{article.url}]({article.url})")
    st.warning("This article has no content sections to extract "
               "(only references or links). Please try another topic.")

elif article is not None:
    # 2) Article info
    st.subheader(article.title)
    st.markdown(f"Source: [{article.url}]({article.url})")

    # 4) Section multiselect
    titles = {}
    for number, title, section in article.sections:
        titles[number] = title
    st.checkbox("Select all sections", key="select_all")
    st.multiselect(
        f"Choose sections ({len(titles)} in this article)",
        list(titles.keys()),
        format_func=lambda number: f"{number}. {titles[number]}",
        key="section_picker",
        disabled=st.session_state.select_all,
    )

    # 5) Extract button
    clicked = st.button("Extract", type="primary", on_click=extract)
    nothing_chosen = not st.session_state.select_all and len(st.session_state.section_picker) == 0
    if clicked and nothing_chosen:
        st.warning("Please choose at least one section before clicking Extract.")

    if st.session_state.text is not None:
        # 6) Preview
        st.subheader(f"Preview - {len(st.session_state.sections_data)} section(s)")
        with st.container(border=True):
            st.code(st.session_state.text, language=None, wrap_lines=True, height=450)

        # 7) Download button - the name is checked against this session's downloads, not the disk
        downloaded = st.session_state.downloaded_filenames
        if numbered_filename(article.title) in downloaded:
            st.warning("You already downloaded a file with this name in this session. "
                       "Downloading again will add a number (e.g. _2) to the name.")
        filename = numbered_filename(article.title, downloaded)
        st.download_button(
            "Download .txt",
            data=st.session_state.text,
            file_name=filename,
            mime="text/plain",
            key="download_btn",
            on_click=record_download,
            args=(filename,),
        )
        st.caption(f"File name: {filename}")


st.divider()
st.caption("Content from Wikipedia, CC BY-SA 4.0.")

# ---------- debugging ----------
with st.expander("Debug: session state"):
    st.write(st.session_state)
