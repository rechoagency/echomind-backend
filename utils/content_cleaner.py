"""
Content Cleaner - Post-processing to fix GPT content violations
Runs after GPT generation to ensure content meets Reddit authenticity standards
"""

import re
import logging

logger = logging.getLogger(__name__)

# Banned phrases - replace with nothing or casual alternatives
PHRASE_REPLACEMENTS = {
    # Generic AI openers
    "seems like a solid choice": "looks decent",
    "looks like a solid choice": "looks decent",
    "is a solid option": "is decent",
    "is a solid choice": "is decent",
    "a solid choice": "a decent pick",
    "solid choice": "decent pick",
    "seems like a great": "looks like a good",
    "seems like a good": "looks good",
    "seems like": "looks like",

    # Wikipedia/formal tone
    "Generally, ": "",
    "Generally speaking, ": "",
    "In general, ": "",
    "It is important to note that ": "",
    "It is important to ": "",
    "It is essential to ": "",
    "It is worth noting that ": "",
    "It is crucial to ": "",
    "It should be noted that ": "",
    "it is important to note that ": "",
    "it is important to ": "",
    "it is essential to ": "",
    "it is worth noting that ": "",
    "it is crucial to ": "",
    "it should be noted that ": "",

    # Corporate/marketing speak
    "If you want to explore other options, consider": "You could also check out",
    "If you want to explore options": "You could also look at",
    "offers advanced features": "has some nice features",
    "provides a good balance": "balances well",
    "from a well-known brand": "",
    "for optimal ": "for best ",
    "ensure optimal": "get the best",

    # Manual-style endings
    "Always check ": "Just double-check ",
    "Always consider ": "Keep in mind ",
    "Always ensure ": "Make sure ",
    "Always verify ": "Double-check ",

    # Other AI patterns
    "Great question!": "",
    "Good question!": "",
    "great question!": "",
    "good question!": "",
    "That's a great question": "",
    "That's a good question": "",
    "don't hesitate to": "feel free to",
    "Don't hesitate to": "Feel free to",

    # AI-style personal experience openers (overused)
    "In my experience, ": "",
    "in my experience, ": "",
    "In my experience,": "",
    "in my experience,": "",
}

# Contractions - must use these (case-sensitive replacements)
CONTRACTION_REPLACEMENTS = {
    "it is ": "it's ",
    "It is ": "It's ",
    "you are ": "you're ",
    "You are ": "You're ",
    "they are ": "they're ",
    "They are ": "They're ",
    "that is ": "that's ",
    "That is ": "That's ",
    "do not ": "don't ",
    "Do not ": "Don't ",
    "does not ": "doesn't ",
    "Does not ": "Doesn't ",
    "cannot ": "can't ",
    "Cannot ": "Can't ",
    "will not ": "won't ",
    "Will not ": "Won't ",
    "would not ": "wouldn't ",
    "Would not ": "Wouldn't ",
    "should not ": "shouldn't ",
    "Should not ": "Shouldn't ",
    "is not ": "isn't ",
    "Is not ": "Isn't ",
    "are not ": "aren't ",
    "Are not ": "Aren't ",
    "have not ": "haven't ",
    "Have not ": "Haven't ",
    "has not ": "hasn't ",
    "Has not ": "Hasn't ",
    "could not ": "couldn't ",
    "Could not ": "Couldn't ",
    "we are ": "we're ",
    "We are ": "We're ",
    "I am ": "I'm ",
    "i am ": "I'm ",
    "I have ": "I've ",
    "i have ": "I've ",
    "you will ": "you'll ",
    "You will ": "You'll ",
    "we have ": "we've ",
    "We have ": "We've ",
    "they have ": "they've ",
    "They have ": "They've ",
}

# Formal words to replace
WORD_REPLACEMENTS = {
    " utilize ": " use ",
    " utilizing ": " using ",
    " purchase ": " buy ",
    " purchasing ": " buying ",
    " requirements ": " what you need ",
    " specifications ": " specs ",
    " functionality ": " features ",
    " aesthetically ": " visually ",
    " accommodate ": " fit ",
    " accommodates ": " fits ",
    " straightforward ": " simple ",
    " Straightforward ": " Simple ",
}

# Price format fixes
PRICE_PATTERN = re.compile(r'\$(\d+)\.00\b')


def clean_content(content: str) -> str:
    """
    Clean GPT-generated content to remove AI patterns and enforce Reddit voice.

    Args:
        content: Raw GPT-generated content

    Returns:
        Cleaned content with violations fixed
    """
    if not content:
        return content

    cleaned = content

    # 1. Fix banned phrases (order matters - longer phrases first)
    sorted_phrases = sorted(PHRASE_REPLACEMENTS.keys(), key=len, reverse=True)
    for phrase in sorted_phrases:
        replacement = PHRASE_REPLACEMENTS[phrase]
        cleaned = cleaned.replace(phrase, replacement)

    # 2. Fix contractions
    for formal, contraction in CONTRACTION_REPLACEMENTS.items():
        cleaned = cleaned.replace(formal, contraction)

    # 3. Fix formal words
    for formal, casual in WORD_REPLACEMENTS.items():
        cleaned = cleaned.replace(formal, casual)

    # 4. Fix price format ($549.00 -> $549)
    cleaned = PRICE_PATTERN.sub(r'$\1', cleaned)

    # 5. Remove tracking links if any slipped through
    cleaned = re.sub(r'\^\(More info:.*?\)', '', cleaned)
    cleaned = re.sub(r'https?://\S*utm_\S*', '', cleaned)

    # 6. Clean up extra whitespace from removals
    cleaned = re.sub(r'  +', ' ', cleaned)
    cleaned = re.sub(r'\n\n+', '\n\n', cleaned)
    cleaned = re.sub(r'^\s+', '', cleaned)  # Leading whitespace
    cleaned = cleaned.strip()

    # 7. Fix sentences that now start with lowercase after removal
    cleaned = re.sub(r'(?<=[.!?]\s)([a-z])', lambda m: m.group(1).upper(), cleaned)

    return cleaned


def validate_content(content: str) -> dict:
    """
    Check if content has any remaining violations after cleaning.

    Returns:
        Dict with 'valid' bool and 'issues' list
    """
    issues = []
    content_lower = content.lower()

    # Check for remaining banned phrases
    banned_check = [
        "seems like", "solid choice", "generally,", "it is important",
        "great question", "good question", "don't hesitate", "in my experience"
    ]
    for phrase in banned_check:
        if phrase in content_lower:
            issues.append(f"Banned phrase: {phrase}")

    # Check for uncontracted forms (common ones only)
    uncontracted_check = [
        ("it is ", "it's"), ("you are ", "you're"), ("do not ", "don't"),
        ("cannot ", "can't"), ("will not ", "won't"), ("i have ", "I've"),
        ("you will ", "you'll"), ("we have ", "we've"), ("they have ", "they've")
    ]
    for formal, contracted in uncontracted_check:
        if formal in content_lower:
            issues.append(f"Missing contraction: {formal.strip()}")

    # Check for tracking links
    if "utm_" in content_lower or "?utm" in content_lower:
        issues.append("Contains tracking link")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'issue_count': len(issues)
    }


def clean_and_validate(content: str) -> tuple:
    """
    Clean content and return both cleaned content and validation result.

    Returns:
        Tuple of (cleaned_content, validation_dict)
    """
    cleaned = clean_content(content)
    validation = validate_content(cleaned)

    if not validation['valid']:
        logger.warning(f"Content still has {validation['issue_count']} issues after cleaning: {validation['issues']}")

    return cleaned, validation
