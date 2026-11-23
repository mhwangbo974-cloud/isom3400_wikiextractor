"""
Logic layer of the Wikipedia Article Extractor.
It never prints or asks for input: errors are stored on the article as self.error,
and the Streamlit app (UI layer) decides how to show them.
"""
from datetime import datetime
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://en.wikipedia.org/wiki/"
HEADERS = {"User-Agent": "ISOM3400-WikiExtractor"}
LICENCE = "CC BY-SA 4.0 (Creative Commons Attribution-ShareAlike 4.0)"


# class part
class WikipediaArticle:
    """
    Fetch one Wikipedia article and extract its sections.
    """
    def __init__(self, topic):
        """
        Parameters:
        topic (str): The topic typed by the user.

        After construction:
        - self.error is None on success, or an error message (str) on failure.
        - self.options is non-empty if the topic is a disambiguation page.
        - self.sections holds (number, title, section_tag) tuples for a normal article.
        """
        self.error = None
        self.url = BASE_URL + topic.replace(" ", "_")
        self.topic = topic
        self.title = None
        self._content = None
        self.options = []           # article titles, only filled for a disambiguation page
        self.sections = []

        try:
            self.fetch()
            if len(self.options) == 0:        # a disambiguation page has no real sections
                self.sections = self.get_sections()
        except requests.exceptions.RequestException as error:
            self.error = f"Network error - could not reach Wikipedia: {error}"
        except ValueError as error:
            self.error = str(error)
        except AttributeError:
            self.error = "Could not read the page."

    def fetch(self):
        """
        Download and parse the article.
        Raises ValueError if the article does not exist or the page layout is unexpected.
        """
        response = requests.get(self.url, headers=HEADERS, timeout=10)
        if response.status_code == 404:
            raise ValueError(f"No Wikipedia article was found for '{self.topic}'.")
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        self._content = soup.select_one("#mw-content-text .mw-parser-output")
        if soup.h1 is None or self._content is None:
            raise ValueError("Unexpected page structure.")
        self.title = soup.h1.get_text(strip=True)

        # A disambiguation page (e.g. "Python") only lists other articles,
        # so collect those article titles for the user to choose from.
        if soup.find(id="disambigbox") is not None:
            for item in self._content.find_all("li"):
                link = item.find("a")
                if link is not None:
                    title = link.get("title", "")
                    if title != "" and ":" not in title and title not in self.options:   # skip special pages
                        self.options.append(title)

    def get_sections(self):
        """
        Return the top-level sections as a list of (number, title, section_tag) tuples.
        """
        sections = []
        for heading in self._content.find_all("div", class_="mw-heading2"):
            title = heading.find("h2").get_text(strip=True)
            sections.append((len(sections) + 1, title, heading.parent))

        if len(sections) == 0:
            raise ValueError("No sections were found.")
        return sections

    def extract_section(self, title, section):
        """
        Return {"title": title, "blocks": [(kind, content), ...]} for one section.
        kind is "subheading", "paragraph", "list" or "table".
        """
        blocks = []
        for tag in section.find_all(["h3", "h4", "p", "ul", "ol", "table"]):
            # Skip tags inside a table or list - the outer tag already covers them.
            if tag.find_parent(["table", "ul", "ol"]) is not None:
                continue

            if tag.name in ["h3", "h4"]:
                blocks.append(("subheading", clean_text(tag)))

            elif tag.name == "p":
                text = clean_text(tag)
                if text != "":
                    blocks.append(("paragraph", text))

            elif tag.name in ["ul", "ol"]:
                items = []
                for li in tag.find_all("li"):
                    if li.find_parent("li") is None:     # nested items are already in their parent item
                        items.append(clean_text(li))
                blocks.append(("list", items))

            elif tag.name == "table" and "wikitable" in tag.get("class", []):
                rows = []
                for tr in tag.find_all("tr"):
                    cells = [clean_text(cell) for cell in tr.find_all(["th", "td"])]
                    if "".join(cells) != "":            # skip rows with no text (e.g. photos only)
                        rows.append(cells)
                blocks.append(("table", rows))

        return {"title": title, "blocks": blocks}


# function part
def clean_text(tag):
    """Return the tag's text without citation markers like [1], with single spaces."""
    text = tag.get_text()
    for extra in tag.find_all("sup", class_="reference") + tag.find_all("style"):
        text = text.replace(extra.get_text(), "")
    return " ".join(text.split())


def safe_filename(title):
    """Turn an article title into a file name without the extension."""
    name = title
    for ch in '\\/:*?"<>|().':                  # characters that do not belong in a file name
        name = name.replace(ch, " ")
    return "_".join(name.split())              # "Python (programming language)" -> "Python_programming_language"


def numbered_filename(title, taken_names=()):
    """
    Build a .txt file name from the article title.
    If the name is in taken_names, add a number: Title_2.txt, Title_3.txt ...
    """
    name = safe_filename(title)
    filename = name + ".txt"
    if filename in taken_names:
        counter = 2
        while f"{name}_{counter}.txt" in taken_names:
            counter += 1
        filename = f"{name}_{counter}.txt"
    return filename


def format_txt(article_title, article_url, sections):
    """Return the header and the extracted sections as one string (the .txt file content)."""
    lines = ["=" * 70,
             article_title,
             "=" * 70,
             f"Source URL : {article_url}",
             f"Extracted  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             f"Licence    : {LICENCE}",
             "=" * 70,
             ""]

    for section in sections:
        lines.append(section["title"].upper())
        lines.append("-" * len(section["title"]))
        for kind, content in section["blocks"]:
            if kind == "subheading":
                lines.append(f"\n## {content}")
            elif kind == "paragraph":
                lines.append(content + "\n")
            elif kind == "list":
                for item in content:
                    lines.append(f"  - {item}")
                lines.append("")
            elif kind == "table":
                for row in content:
                    lines.append("| " + " | ".join(row) + " |")
                lines.append("")
        lines.append("")

    return "\n".join(lines)
