"""
Incremental sentence-boundary chunker for text arriving in small pieces over
time (e.g. token/delta chunks from a streaming LLM response), as opposed to
tts/piper_tts.py::split_sentences_smoothly(), which only ever operates on a
single, already-complete string.

This is a genuinely different problem from batch sentence splitting: a "."
sitting at the tail of the text buffered *so far* might just be the end of
an abbreviation ("Dr.") whose continuation hasn't arrived yet, so a sentence
can only be confirmed complete once enough *following* text has arrived to
disambiguate it. When no more text is coming (the stream has ended), any
text still held back is returned via flush() instead, even if it never
picked up trailing punctuation.

This is Step 1 of the streaming-TTS rewrite (see CHANGELOG.md and
PHASES.md Phase 6). It is deliberately standalone: it does not import
anything from brain/, tts/, or orchestrator.py, and is not wired into the
live pipeline yet.
"""

from typing import List, Optional


class SentenceChunker:
    """
    Buffers incrementally-arriving text and yields complete sentences as
    soon as enough context has arrived to confirm a sentence boundary,
    holding back ambiguous cases until more text disambiguates them.

    Heuristic (deliberately simple -- a "good enough, not obviously wrong
    on common cases" rule set, not a full NLP sentence tokenizer). A '.',
    '!', or '?' is treated as a CONFIRMED sentence end only if all of the
    following hold:

      1. Decimal-number guard: a '.' is never a boundary if it has a digit
         immediately on both sides (e.g. the '.' in "3.14"). Checked first,
         directly on the characters adjacent to the dot -- independent of
         rule 4 below, since a decimal's two halves are never separated by
         whitespace, so it wouldn't require this special case in practice,
         but it's kept explicit since decimal numbers were a named
         requirement and this makes that guarantee non-accidental.

      2. Terminator-run collapsing: a run of terminator characters
         ("...", "?!", "!?", etc.) is only ever evaluated at its LAST
         character -- earlier characters in the run are skipped outright.
         This also gives ellipsis handling "for free": "Wait... what?" is
         not split at the ellipsis because the word after it ("what")
         starts lowercase and fails rule 4; "Wait... What?" (capitalized)
         *is* split there, which is a reasonable reading of a dramatic
         pause introducing a new sentence.

      3. Abbreviation / initial guard: the text immediately preceding a
         '.' is checked against a small list of common abbreviations
         (Mr, Dr, e.g, etc, ...) -- including multi-part dotted ones like
         "e.g"/"i.e", matched by suffix rather than by a trailing-word scan
         so the internal dot doesn't truncate the match -- and against the
         single-letter-initial
         pattern (a lone capital letter, as in the "K." in "J. K. Rowling")
         -- both suppress the boundary.

      4. Lookahead confirmation: the terminator must be followed by
         whitespace and then a character that plausibly starts a new
         sentence (an uppercase letter, a digit, or an opening quote/
         paren). If the currently buffered text simply runs out before
         this can be determined (nothing has arrived yet after the
         terminator, or after the whitespace that follows it), the
         boundary is treated as NOT YET confirmed and more text is
         awaited -- this is the core streaming-specific behavior that a
         batch splitter never needs.

    Known limitation (acceptable per the "reasonable heuristic" bar this
    was built to): if a genuine new sentence happens to start with a
    lowercase word (rare in well-formed English/LLM output), it will not
    be confirmed until further text arrives to prove a sentence boundary
    exists some other way, or until flush() is called at the end of the
    stream.
    """

    ABBREVIATIONS = {
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
        "e.g", "i.e", "inc", "ltd", "approx", "no", "vol", "fig",
        "st", "ave", "co", "corp", "dept", "est", "gov", "univ",
    }

    _TERMINATOR_CHARS = ".!?"
    _CLOSING_CHARS = "\"')]”’"
    _SENTENCE_START_CHARS = "\"'([“‘"

    def __init__(self):
        self._buffer: str = ""

    def add_chunk(self, chunk: str) -> List[str]:
        """
        Appends an incoming text chunk to the internal buffer and returns a
        list of zero or more sentences that are now confirmed complete (in
        order). Any remaining, not-yet-confirmed text stays buffered
        internally for the next call.
        """
        if chunk:
            self._buffer += chunk
        return self._extract_ready_sentences()

    def flush(self) -> Optional[str]:
        """
        Call once the stream has ended. Returns whatever text remains
        buffered (stripped) as a final "sentence" -- even if it never
        ended in punctuation -- or None if nothing is left. Resets the
        internal buffer, so the chunker is ready to be reused for a new
        stream afterward.
        """
        remaining = self._buffer.strip()
        self._buffer = ""
        return remaining if remaining else None

    def _extract_ready_sentences(self) -> List[str]:
        sentences = []
        while True:
            boundary = self._find_confirmed_boundary(self._buffer)
            if boundary is None:
                break
            sentence = self._buffer[:boundary].strip()
            self._buffer = self._buffer[boundary:].lstrip()
            if sentence:
                sentences.append(sentence)
        return sentences

    def _find_confirmed_boundary(self, text: str) -> Optional[int]:
        """
        Scans text for the first CONFIRMED sentence-terminator and returns
        the buffer index immediately after it (and after any trailing
        whitespace), or None if no confirmed boundary exists yet.
        """
        n = len(text)
        i = 0
        while i < n:
            if text[i] not in self._TERMINATOR_CHARS:
                i += 1
                continue

            # Rule 2: collapse a run of terminator chars -- only consider
            # the LAST character of the run as a candidate boundary.
            run_end = i
            while run_end + 1 < n and text[run_end + 1] in self._TERMINATOR_CHARS:
                run_end += 1
            if run_end != i:
                i = run_end
                continue
            term_char = text[i]

            # Rule 1: decimal-number guard, checked directly on adjacent chars.
            if term_char == "." and i > 0 and text[i - 1].isdigit() and i + 1 < n and text[i + 1].isdigit():
                i += 1
                continue

            # Absorb trailing closing quotes/parens into the sentence itself.
            end = i + 1
            while end < n and text[end] in self._CLOSING_CHARS:
                end += 1

            # Rule 4a: must be followed by whitespace. If we're at the end
            # of the buffer with nothing after the terminator yet, wait.
            if end >= n or not text[end].isspace():
                i += 1
                continue

            k = end
            while k < n and text[k].isspace():
                k += 1
            if k >= n:
                # Whitespace runs out to the end of the buffer -- the next
                # sentence's first character hasn't arrived yet. Wait.
                i += 1
                continue

            next_char = text[k]
            if not (next_char.isupper() or next_char.isdigit() or next_char in self._SENTENCE_START_CHARS):
                i += 1
                continue

            # Rule 3: abbreviation / single-letter-initial guard (dots only).
            if term_char == ".":
                if self._is_preceded_by_abbreviation(text, i):
                    i += 1
                    continue
                word_before = self._word_before(text, i)
                if len(word_before) == 1 and word_before.isupper():
                    i += 1
                    continue

            return k

        return None

    @staticmethod
    def _word_before(text: str, dot_index: int) -> str:
        """Returns the run of alphabetic characters immediately preceding dot_index."""
        start = dot_index
        while start > 0 and text[start - 1].isalpha():
            start -= 1
        return text[start:dot_index]

    def _is_preceded_by_abbreviation(self, text: str, end_index: int) -> bool:
        """
        Checks whether text[:end_index] ends with a known abbreviation
        (case-insensitively), including multi-part dotted ones like "e.g"
        or "i.e" -- a plain trailing-alphabetic-run check (as used for the
        single-letter-initial rule) can't detect these, since the internal
        dot in "e.g" would stop that scan after just the "g".
        """
        lowered = text[:end_index].lower()
        for abbr in self.ABBREVIATIONS:
            if lowered.endswith(abbr):
                start = end_index - len(abbr)
                # Guard against matching inside a longer word/token
                # (e.g. don't let "sr" match the tail of some other word).
                if start == 0 or not text[start - 1].isalpha():
                    return True
        return False
