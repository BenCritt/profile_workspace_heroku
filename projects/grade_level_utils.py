import re
import textstat

def _sanitize_for_readability(s: str) -> str:
    """Normalize punctuation and whitespace."""
    s = s.replace("—", " ").replace("–", " ").replace("…", ". ")
    s = s.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'}))
    # Remove standalone numbers/ordinals that can trip syllable tokenizers
    s = re.sub(r"\b\d+(?:[.,]\d+)?(?:st|nd|rd|th)?\b", " ", s)
    # Collapse whitespace
    return re.sub(r"\s{2,}", " ", s).strip()

def _sentences(s: str):
    return [x for x in re.split(r"[.!?]+", s) if x.strip()]

def _words(s: str):
    # keep contractions as a single token
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", s)

def _syllables(word: str) -> int:
    _vowels = set("aeiouy")
    w = word.lower()
    count, prev_vowel = 0, False
    for ch in w:
        is_vowel = ch in _vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Drop a trailing silent 'e' when plausible
    if w.endswith("e") and count > 1:
        count -= 1
    return max(count, 1)

def _metrics(s: str):
    """
    Naive, dependency-free readability estimators 
    (Fallback if textstat fails).
    """
    # Keep letters, digits, basic punctuation; normalize whitespace
    s2 = re.sub(r"[^A-Za-z0-9\.\!\?,;:\s']", " ", s)
    s2 = re.sub(r"\s{2,}", " ", s2).strip()
    sents = _sentences(s2) or [s2]
    words = _words(s2)
    n_w = max(len(words), 1)
    n_s = max(len(sents), 1)
    n_letters = sum(len(re.findall(r"[A-Za-z]", w)) for w in words)
    syl_per_word = (sum(_syllables(w) for w in words) / n_w) if n_w else 0.0
    words_per_sent = n_w / n_s
    
    # Flesch–Kincaid Grade
    fk = 0.39 * words_per_sent + 11.8 * syl_per_word - 15.59
    
    # Coleman–Liau Index
    L = (n_letters / n_w) * 100.0
    S = (n_s / n_w) * 100.0
    cli = 0.0588 * L - 0.296 * S - 15.8
    
    # Gunning Fog
    complex_words = sum(1 for w in words if _syllables(w) >= 3)
    fog = 0.4 * (words_per_sent + 100.0 * (complex_words / n_w))
    
    return fk, fog, cli

def calculate_grade_levels(input_text):
    """
    Main public function to process text and return a dictionary of scores.
    """
    # If available, ensure English rules for textstat
    if hasattr(textstat, "set_lang"):
        try:
            textstat.set_lang("en_US")
        except Exception:
            pass

    clean_text = _sanitize_for_readability(input_text)
    
    # Calculate scores (Try textstat first, fallback to manual _metrics)
    try:
        results = {
            "flesch_kincaid_grade": textstat.flesch_kincaid_grade(clean_text),
            "gunning_fog":          textstat.gunning_fog(clean_text),
            "coleman_liau_index":   textstat.coleman_liau_index(clean_text),
        }
    except (KeyError, Exception):
        # Fallback for dictionary misses or other errors
        fk, fog, cli = _metrics(clean_text)
        results = {
            "flesch_kincaid_grade": fk,
            "gunning_fog":          fog,
            "coleman_liau_index":   cli,
        }

    # Calculate averages
    results["average_score"] = round(
        (0.5 * results["flesch_kincaid_grade"])
        + (0.3 * results["gunning_fog"])
        + (0.2 * results["coleman_liau_index"]),
        1,
    )
    
    results["uniform_average_score"] = round(
        (
            results["flesch_kincaid_grade"]
            + results["gunning_fog"]
            + results["coleman_liau_index"]
        )
        / 3,
        1,
    )

    # Add Stats for display
    # Note: We recalculate basic stats here for display purposes using our safe tokenizers
    words = _words(clean_text)
    sents = _sentences(clean_text)
    results["word_count"] = len(words)
    results["sentence_count"] = len(sents)
    results["syllable_count"] = sum(_syllables(w) for w in words)

    return results