"""
Content Generation Worker - COMPLETE OVERHAUL v2.0
Generates natural Reddit responses with anti-AI detection and voice matching
"""

import os
import logging
import json
import random
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
from supabase import create_client, Client
from openai import OpenAI
import sys
import os

# Traffic attribution for business ROI (import with fallback)
try:
    from utils.utm_builder import inject_link_naturally
except ImportError:
    inject_link_naturally = None  # Will log warning after logger is configured

# Post-processing to fix GPT violations
try:
    from utils.content_cleaner import clean_content
except ImportError:
    clean_content = None  # Will work without if not available

# Add parent directory to path for service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.profile_rotation_service import ProfileRotationService
from services.strategy_progression_service import StrategyProgressionService
from services.knowledge_matchback_service import KnowledgeMatchbackService
from utils.retry_decorator import retry_on_openai_error


# ═══════════════════════════════════════════════════════════════════════════════
# ANTI-AI DETECTION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

AI_FORBIDDEN_PATTERNS = [
    # Hyphens and dashes
    r'—',  # em dash
    r'–',  # en dash
    # Bullet points and lists
    r'^\s*[-•*]\s',  # bullet points at start of line
    r'^\s*\d+\.\s',  # numbered lists
    # AI-typical phrases
    r'\bI understand\b',
    r'\bI hear you\b',
    r"\bHere's what I (think|recommend|suggest)\b",
    r"\bI would (suggest|recommend)\b",
    r'\bThat said\b',
    r'\bThat being said\b',
    r'\bHope this helps\b',
    r"\bFeel free to\b",
    r"\bDon't hesitate to\b",
    r'\bAbsolutely!\b',
    r'\bGreat question\b',
    r'\bThanks for (sharing|asking|reaching)\b',
]

AI_FORBIDDEN_STARTERS = [
    'So,',
    'Well,',
    'Honestly,',
    'Actually,',
    'Look,',
    'Here\'s the thing',
    'I\'d say',
    'I think',
    'In my opinion',
    'From my experience',
]

# Common typos to inject based on keyboard proximity
TYPO_SUBSTITUTIONS = {
    'the': ['teh', 'hte'],
    'and': ['adn', 'nad'],
    'with': ['wiht', 'wtih'],
    'that': ['taht', 'tath'],
    'have': ['ahve', 'hvae'],
    'just': ['jsut', 'jutst'],
    'your': ['yoru', 'yuor'],
    'this': ['thsi', 'tihs'],
    'really': ['realy', 'realyl'],
    'definitely': ['definately', 'definitly', 'definetly'],
    'probably': ['probaly', 'prolly'],
    'would': ['woudl', 'wuold'],
    'could': ['coudl', 'cuold'],
    'should': ['shoudl', 'shuold'],
    'because': ['becuase', 'becasue', 'bc'],
    'through': ['thru', 'thorugh'],
    'though': ['tho', 'thoguh'],
    'something': ['somethign', 'somethin'],
    'anything': ['anythign', 'anythin'],
}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# OpenAI client with timeout (30 seconds)
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)


class ContentGenerationWorker:
    """
    Worker that generates Reddit responses with anti-AI detection and voice matching
    """

    def __init__(self):
        """Initialize the content generation worker"""
        self.supabase = supabase
        self.openai = openai_client
        self.profile_rotation = ProfileRotationService()
        self.strategy_progression = StrategyProgressionService()
        self.knowledge_matchback = KnowledgeMatchbackService(supabase)
        logger.info("Content Generation Worker v2.0 initialized (ANTI-AI DETECTION + VOICE MATCHING)")

    # ═══════════════════════════════════════════════════════════════════════════
    # ANTI-AI DETECTION & HUMANIZATION FUNCTIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def detect_ai_patterns(self, content: str) -> List[str]:
        """
        Detect AI-typical patterns in generated content.
        Returns list of violations found.
        """
        violations = []

        # Check forbidden patterns
        for pattern in AI_FORBIDDEN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE | re.MULTILINE):
                violations.append(f"Pattern: {pattern}")

        # Check forbidden starters
        content_stripped = content.strip()
        for starter in AI_FORBIDDEN_STARTERS:
            if content_stripped.startswith(starter):
                violations.append(f"Starter: {starter}")

        # Check for consistent sentence starters (AI tends to repeat patterns)
        sentences = re.split(r'[.!?]\s+', content)
        if len(sentences) >= 3:
            starters = [s.split()[0].lower() if s.split() else '' for s in sentences[:5]]
            if len(starters) > 0 and starters.count(starters[0]) >= 3:
                violations.append(f"Repeated starter: {starters[0]}")

        return violations

    def inject_typos(self, content: str, typo_count: int = 1) -> str:
        """
        Inject natural-looking typos into content.
        Only injects into words that appear in TYPO_SUBSTITUTIONS.
        """
        if typo_count <= 0:
            return content

        words = content.split()
        typo_candidates = []

        # Find words that can have typos
        for i, word in enumerate(words):
            word_lower = word.lower().strip('.,!?;:')
            if word_lower in TYPO_SUBSTITUTIONS:
                typo_candidates.append((i, word_lower, word))

        # Randomly select words to typo
        if typo_candidates:
            selected = random.sample(typo_candidates, min(typo_count, len(typo_candidates)))
            for idx, word_lower, original in selected:
                typo = random.choice(TYPO_SUBSTITUTIONS[word_lower])
                # Preserve original casing and punctuation
                if original[0].isupper():
                    typo = typo.capitalize()
                # Preserve trailing punctuation
                trailing = ''
                for char in reversed(original):
                    if char in '.,!?;:':
                        trailing = char + trailing
                    else:
                        break
                words[idx] = typo + trailing

        return ' '.join(words)

    def apply_lowercase_starts(self, content: str, lowercase_pct: float) -> str:
        """
        Randomly lowercase sentence starts based on percentage.
        """
        if lowercase_pct <= 0:
            return content

        sentences = re.split(r'([.!?]\s+)', content)
        result = []

        for i, part in enumerate(sentences):
            if i % 2 == 0 and part:  # This is a sentence, not punctuation
                if random.random() * 100 < lowercase_pct and len(part) > 0:
                    # Lowercase the first character
                    part = part[0].lower() + part[1:] if len(part) > 1 else part.lower()
            result.append(part)

        return ''.join(result)

    def vary_contractions(self, content: str, contraction_rate: float) -> str:
        """
        Randomly expand or contract words based on contraction rate.
        """
        # Expansion pairs (contracted -> expanded)
        expansions = {
            "don't": "do not",
            "can't": "cannot",
            "won't": "will not",
            "wouldn't": "would not",
            "couldn't": "could not",
            "shouldn't": "should not",
            "isn't": "is not",
            "aren't": "are not",
            "wasn't": "was not",
            "weren't": "were not",
            "haven't": "have not",
            "hasn't": "has not",
            "hadn't": "had not",
            "it's": "it is",
            "that's": "that is",
            "there's": "there is",
            "here's": "here is",
            "what's": "what is",
            "who's": "who is",
            "i'm": "I am",
            "you're": "you are",
            "we're": "we are",
            "they're": "they are",
            "i've": "I have",
            "you've": "you have",
            "we've": "we have",
            "they've": "they have",
            "i'd": "I would",
            "you'd": "you would",
            "we'd": "we would",
            "they'd": "they would",
            "i'll": "I will",
            "you'll": "you will",
            "we'll": "we will",
            "they'll": "they will",
        }

        # If high contraction rate, keep contractions; if low, expand some
        if contraction_rate > 50:
            return content  # Keep as-is (likely already has contractions)

        # Randomly expand some contractions
        for contracted, expanded in expansions.items():
            if contracted in content.lower():
                # Find and replace with probability based on rate
                if random.random() * 100 > contraction_rate:
                    # Case-insensitive replacement
                    pattern = re.compile(re.escape(contracted), re.IGNORECASE)
                    content = pattern.sub(expanded, content, count=1)

        return content

    def generate_voice_similarity_proof(
        self,
        voice_profile: Dict,
        content: str,
        subreddit: str
    ) -> str:
        """
        Generate explanation of how content matches the subreddit voice.
        This goes in the Voice Similarity Proof column of the Excel.
        """
        proofs = []

        vp = voice_profile.get('voice_profile', voice_profile) if voice_profile else {}

        # Tone match
        tone = vp.get('dominant_tone') or vp.get('tone', 'conversational')
        proofs.append(f"Tone: {tone}")

        # Formality match
        formality = vp.get('formality_score', 0.5)
        if formality < 0.3:
            proofs.append("casual/informal register")
        elif formality < 0.6:
            proofs.append("conversational register")
        else:
            proofs.append("semi-formal register")

        # Check for unique vocabulary used
        unique_vocab = vp.get('unique_vocabulary', [])
        content_lower = content.lower()
        vocab_used = [v for v in unique_vocab[:10] if v.lower() in content_lower]
        if vocab_used:
            proofs.append(f"community vocab: {', '.join(vocab_used[:3])}")

        # Check for common phrases used
        common_phrases = vp.get('common_phrases', [])
        phrases_used = [p for p in common_phrases[:10] if p.lower() in content_lower]
        if phrases_used:
            proofs.append(f"natural phrasing")

        # Word count analysis
        avg_words = vp.get('avg_word_count', 75)
        actual_words = len(content.split())
        if abs(actual_words - avg_words) < avg_words * 0.3:
            proofs.append(f"length matches r/{subreddit} avg")

        return "; ".join(proofs) if proofs else "Matches general subreddit tone"

    def calculate_target_word_count(self, voice_profile: Dict) -> int:
        """
        Calculate target word count with ±30% variation from voice profile average.
        """
        vp = voice_profile.get('voice_profile', voice_profile) if voice_profile else {}
        avg_words = vp.get('avg_word_count', 75)

        # Apply ±30% variation
        min_words = int(avg_words * 0.7)
        max_words = int(avg_words * 1.3)

        return random.randint(min_words, max_words)

    def get_formality_level(self, score: float) -> str:
        """Convert formality score to human-readable level."""
        if score < 0.3:
            return "very casual"
        elif score < 0.5:
            return "casual"
        elif score < 0.7:
            return "conversational"
        else:
            return "semi-formal"

    @retry_on_openai_error(max_attempts=3)
    def _call_openai_with_retry(self, prompt: str, max_tokens: int = 250) -> str:
        """Call OpenAI API with automatic retry and exponential backoff."""
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",  # Upgraded from gpt-4 for better performance
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please write the response now."}
                ],
                temperature=0.8,
                max_tokens=max_tokens
            )
            raw_content = response.choices[0].message.content.strip()

            # Post-process to fix GPT violations (banned phrases, contractions, etc.)
            if clean_content:
                return clean_content(raw_content)
            return raw_content
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def get_client_settings(self, client_id: str) -> Dict:
        """
        Load client settings including slider values and special instructions.
        Returns defaults if no settings found.
        """
        try:
            response = self.supabase.table('client_settings') \
                .select('*') \
                .eq('client_id', client_id) \
                .single() \
                .execute()
            
            if response.data:
                logger.info(f"✅ Loaded settings for client {client_id}")
                return {
                    'reply_percentage': response.data.get('reply_percentage', 70),
                    'brand_mention_percentage': response.data.get('brand_mention_percentage', 30),
                    'product_mention_percentage': response.data.get('product_mention_percentage', 20),
                    'explicit_instructions': response.data.get('explicit_instructions', '')
                }
            else:
                logger.warning(f"⚠️ No settings found for client {client_id}, using defaults")
                return {
                    'reply_percentage': 70,
                    'brand_mention_percentage': 30,
                    'product_mention_percentage': 20,
                    'explicit_instructions': ''
                }
        except Exception as e:
            logger.error(f"❌ Error loading client settings: {e}")
            return {
                'reply_percentage': 70,
                'brand_mention_percentage': 30,
                'product_mention_percentage': 20,
                'explicit_instructions': ''
            }
    
    def should_mention_brand(self, brand_mention_percentage: int) -> bool:
        """Probabilistically decide if brand should be mentioned"""
        return random.randint(1, 100) <= brand_mention_percentage
    
    def should_mention_product(self, product_mention_percentage: int, similarity_score: float) -> bool:
        """
        Decide if product should be mentioned.
        ONLY applies when vector similarity >= 0.75 (75%)
        """
        if similarity_score < 0.75:
            return False
        return random.randint(1, 100) <= product_mention_percentage
    
    # Fallback voice profile for when subreddit-specific profile is missing
    FALLBACK_VOICE_PROFILE = {
        # Length patterns
        "avg_word_count": 75,
        "word_count_range": {"min": 30, "max": 200},
        "short_reply_probability": 0.4,
        "avg_word_length": 4.5,

        # Grammar patterns
        "capitalization_style": "mixed",
        "lowercase_start_pct": 25,
        "contraction_rate": 5.0,

        # Lexical patterns - DYNAMIC (learned from actual subreddit data)
        "common_phrases": ["honestly", "in my experience", "typically", "depends on"],
        "unique_vocabulary": [],  # Learned words unique to this community
        "abbreviations_slang": [],  # Learned abbreviations/slang
        "signature_idioms": [],
        "vocabulary_richness": 0,

        # Emoji patterns
        "emoji_frequency": "rare",
        "common_emojis": [],

        # Tone patterns - DYNAMICALLY CALCULATED
        "dominant_tone": "helpful, direct",
        "tone": "supportive, conversational",
        "grammar_style": "casual with informal patterns",
        "formality_score": 0.35,
        "formality_level": "LOW",
        "formality_breakdown": {
            "word_length": 0.33,
            "capitalization": 0.58,
            "contractions": 0.50,
            "exclamations": 0.47,
            "first_person": 0.20
        },

        # Content patterns
        "example_openers": [],
        "example_closers": [],
        "question_frequency": 0.1,
        "exclamation_usage_pct": 5,
        "hedging_frequency": 0.02,

        # Metadata
        "voice_description": "Default Reddit community voice. Friendly and authentic.",
        "sample_comments": [],
        "users_analyzed": 0,
        "comments_analyzed": 0,
        "is_fallback": True,
        "learning_method": "fallback"
    }

    def get_voice_profile(self, subreddit_name: str, client_id: str) -> Optional[Dict]:
        """
        Get voice profile for a subreddit.
        Returns fallback profile if none found (ensures content always sounds human).
        Note: voice_database_worker saves to 'subreddit' column, not 'subreddit_name'
        """
        try:
            # Try 'subreddit' column first (what voice_database_worker uses)
            profile = self.supabase.table("voice_profiles")\
                .select("*")\
                .eq("subreddit", subreddit_name.lower())\
                .eq("client_id", client_id)\
                .execute()

            if profile.data:
                return profile.data[0]

            # Return fallback profile instead of None
            logger.warning(f"No voice profile found for r/{subreddit_name} - using fallback voice")
            return self.FALLBACK_VOICE_PROFILE

        except Exception as e:
            logger.error(f"Error fetching voice profile: {str(e)} - using fallback")
            return self.FALLBACK_VOICE_PROFILE
    
    def build_generation_prompt(
        self,
        opportunity: Dict,
        voice_profile: Optional[Dict],
        product_matches: Optional[Dict],
        knowledge_insights: Optional[List[Dict]],
        client_settings: Dict,
        mention_brand: bool,
        mention_product: bool,
        brand_name: str,
        client_data: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        Build the complete prompt for GPT-4 content generation.
        COMPLETELY REWRITTEN for anti-AI detection.

        Returns:
            Tuple of (prompt string, voice_params dict for post-processing)
        """
        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text", "")
        subreddit = opportunity.get("subreddit", "")

        # Extract voice parameters for post-processing
        vp = {}
        if voice_profile:
            vp = voice_profile.get('voice_profile', voice_profile)

        formality = vp.get('formality_score', 0.5)
        formality_level = self.get_formality_level(formality)
        avg_words = vp.get('avg_word_count', 75)
        target_words = self.calculate_target_word_count(voice_profile or {})
        lowercase_pct = vp.get('lowercase_start_pct', 15)
        contraction_rate = vp.get('contraction_rate', 50)
        exclamation_pct = vp.get('exclamation_usage_pct', 5)
        tone = vp.get('dominant_tone') or vp.get('tone', 'helpful, direct')
        unique_vocab = vp.get('unique_vocabulary', [])[:5]
        common_phrases = vp.get('common_phrases', [])[:3]

        # Calculate typo count based on formality
        typo_count = 0
        if formality < 0.4:
            typo_count = random.choice([0, 1, 1])  # Sometimes add typo in casual subs
        elif formality < 0.6:
            typo_count = random.choice([0, 0, 1])  # Rarely add typo

        # Voice parameters for post-processing
        voice_params = {
            'formality': formality,
            'lowercase_pct': lowercase_pct,
            'contraction_rate': contraction_rate,
            'typo_count': typo_count,
            'target_words': target_words,
            'tone': tone,
        }

        # Check if brand owns this subreddit
        owned_subreddits = []
        if client_data:
            owned_subreddits = client_data.get('owned_subreddits', []) or client_data.get('brand_owned_subreddits', [])
        is_owned = subreddit in owned_subreddits or f"r/{subreddit}" in owned_subreddits

        # Build knowledge context - CRITICAL: Include specific details
        knowledge_text = ""
        has_knowledge = knowledge_insights and len(knowledge_insights) > 0
        if has_knowledge:
            knowledge_text = "\n".join([
                f"- {insight.get('excerpt', insight.get('chunk_text', ''))[:500]}"
                for insight in knowledge_insights[:3]
            ])

        # Build unique vocab string
        vocab_str = ", ".join(unique_vocab) if unique_vocab else "none"
        phrases_str = ", ".join(f'"{p}"' for p in common_phrases) if common_phrases else "none"

        # Brand mention context
        brand_context = ""
        if is_owned:
            brand_context = f"This is {brand_name}'s own subreddit. You can be promotional."
        elif mention_brand or mention_product:
            brand_context = f"You MAY mention {brand_name} as ONE option (not the only one). Be honest about limitations."
        else:
            brand_context = "Do NOT mention brand or products. Focus on general helpful advice."

        # ═══════════════════════════════════════════════════════════════════════
        # THE NEW ANTI-AI PROMPT STRUCTURE
        # ═══════════════════════════════════════════════════════════════════════

        prompt = f"""You are writing a Reddit reply as a real community member of r/{subreddit}.

VOICE PROFILE FOR r/{subreddit}:
- Formality: {formality:.2f} ({formality_level})
- Tone: {tone}
- Target reply length: {target_words} words (THIS IS IMPORTANT - vary naturally)
- Lowercase sentence starts: {lowercase_pct}% of the time
- Exclamation usage: {exclamation_pct}%
- Contraction rate: {contraction_rate}%
- Unique vocabulary to use naturally: {vocab_str}
- Common phrases in this community: {phrases_str}

THREAD CONTEXT:
Subreddit: r/{subreddit}
Title: {thread_title}
Original post: {thread_content[:1500] if thread_content else '[No content]'}

{f'''═══════════════════════════════════════════════════════════════════════════════
KNOWLEDGE BASE + INDUSTRY EXPERTISE
═══════════════════════════════════════════════════════════════════════════════

CLIENT KNOWLEDGE BASE (PRIORITY SOURCE - use exact facts):
{knowledge_text}

KNOWLEDGE SOURCING RULES:

1. PRIORITIZE CLIENT KNOWLEDGE: Use exact numbers, prices, and model names from above.
   If it says "$549" use "$549". If it says "Sideline Elite 50" use that exact name.

2. SUPPLEMENT WITH INDUSTRY EXPERTISE: You may add general industry knowledge that
   GPT-4 knows, such as:
   - "240V electric maxes out around 10,000 BTU"
   - "Most wall-mounted units need 4-6 inches of recessed depth"
   - "LED flame technology uses about 10-15 watts"

3. CLEARLY DISTINGUISH SOURCES:
   - Client products: Use specific model names and prices from knowledge above
   - General facts: Frame as industry knowledge ("generally", "most units", "typically")

4. NEVER CONTRADICT CLIENT DATA: If knowledge says a specific spec, use it exactly.
   Only supplement with general facts where client data has gaps.

5. EXAMPLE OF GOOD SOURCING:
   "The Sideline Elite 50 runs about $699 with 5000 BTU output [from knowledge].
   For context, 240V electric typically maxes around 10,000 BTU [industry knowledge],
   so this is solid mid-range heat for most living rooms."
''' if has_knowledge else ""}

BRAND CONTEXT: {brand_context}

═══════════════════════════════════════════════════════════════════════════════
BANNED PHRASES (NEVER use - instant AI detection)
═══════════════════════════════════════════════════════════════════════════════

BANNED OPENERS AND PHRASES:
- "seems like a solid choice" / "looks like a solid choice" / "is a solid option"
- "Generally, ..." / "It is important to note..." / "It is essential to..."
- "If you want to explore other options, consider..."
- "Always check..." / "Always consider..." / "Always ensure..."
- "from a well-known brand" / "There should be models..."
- "offers advanced features" / "provides a good balance"
- "for optimal [anything]" / "ensure optimal"
- "I understand your situation" / "I hear you"
- "Here's what I think/recommend/suggest"
- "That said" / "That being said"
- "Hope this helps" / "Feel free to ask"
- "Absolutely!" / "Great question!"

BANNED WORDS (replace with casual alternatives):
- "features" -> "has" or "comes with"
- "offers" -> "has" or "comes with"
- "available for" -> "runs about" or "costs"
- "ensure" -> "make sure"
- "accommodate" -> "fit" or "handle"
- "utilize" -> "use"
- "consider" -> "check out" or "look at"
- "purchasing" -> "buying" or "getting"
- "requirements" -> "what you need"
- "specifications" -> "specs"
- "functionality" -> cut it or "what it does"
- "aesthetically" -> "looks"
- "optimal" -> "best" or cut it
- "essential" -> "important" or cut it
- "crucial" -> "important" or cut it

═══════════════════════════════════════════════════════════════════════════════
REQUIRED CONTRACTIONS (always use these - no formal writing)
═══════════════════════════════════════════════════════════════════════════════

ALWAYS contract:
- "it is" -> "it's"
- "you are" -> "you're"
- "they are" -> "they're"
- "that is" -> "that's"
- "do not" -> "don't"
- "does not" -> "doesn't"
- "cannot" -> "can't"
- "will not" -> "won't"
- "would not" -> "wouldn't"
- "should not" -> "shouldn't"
- "is not" -> "isn't"
- "are not" -> "aren't"

═══════════════════════════════════════════════════════════════════════════════
OPENING AND STRUCTURE VARIETY (critical for avoiding spam detection)
═══════════════════════════════════════════════════════════════════════════════

VARY YOUR OPENING (never use same pattern twice):
- Start with direct answer to their question
- Start with acknowledgment of their situation (but not "I understand")
- Start with a specific fact relevant to their question
- Start with a clarifying question back to OP
- Skip validation entirely and just give advice
- NEVER start with: So, Well, Honestly, Actually, Look, Here's the thing

VARY YOUR STRUCTURE (pick different patterns):
Pattern A: Direct answer -> Supporting fact -> Done
Pattern B: Acknowledge situation -> Specific recommendation -> Why
Pattern C: Answer question -> Related tip -> Done
Pattern D: Specific fact first -> How it applies to them
Pattern E: Counter-intuitive insight -> Explanation

═══════════════════════════════════════════════════════════════════════════════
VOICE RULES (Brand Account Voice - NOT fake customer)
═══════════════════════════════════════════════════════════════════════════════

- You are writing AS THE BRAND, not as a fake customer
- NEVER use first-person testimonials: "I bought...", "I installed...", "I love my..."
- USE helpful advisor voice: "The Sideline Elite 50 runs about $699..."
- USE third-person expertise: "Most customers find...", "The unit provides..."
- BE DIRECT with product info: "This model has 60 flame colors and 5000 BTU output"

PRICE FORMAT:
- WRONG: "$549.00"
- RIGHT: "$549" or "around $550" or "~$550"

PRODUCT NAME FORMAT:
- First mention: "Touchstone Forte 40"
- After that: "the Forte 40" or "Forte" or "that model"
- NEVER: "Forte 40 Inch Recessed Smart Electric Fireplace" (too long)

═══════════════════════════════════════════════════════════════════════════════
EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

BAD (AI-detectable):
"The TURBRO 72 Inch Wall Mounted Electric Fireplace seems like a solid choice, especially if the reviews are positive and it is within your budget. Generally, wall-mounted electric fireplaces are popular for their ease of installation and modern look. If you want to explore other options, consider the Forte 40 Inch Recessed Smart Electric Fireplace, which is priced at $549.00 and features six flame colors."

GOOD (human-like):
"The TURBRO's decent from what I've seen. If you're looking at wall-mounted units you'll want about 4-6 inches of wall depth for most of them. The 240V models max out around 10k BTU so heat output's pretty similar across brands at that voltage."

NOTE: The good example doesn't always mention the brand - that's intentional based on brand_mention_percentage settings.

═══════════════════════════════════════════════════════════════════════════════

LENGTH: Write 50-200 words depending on what's typical for the subreddit. Match the natural length of replies in that community - some subreddits have shorter casual replies, others have longer detailed discussions. ONE paragraph unless the subreddit typically uses longer formats. No tracking links. No URLs.
Sound like a helpful stranger on Reddit, not a product guide.
End naturally - no call to action, no "hope this helps", no summary.

OUTPUT ONLY THE REPLY TEXT - nothing else."""

        return prompt, voice_params
    
    def generate_content_for_client(
        self,
        client_id: str,
        opportunities: List[Dict],
        delivery_batch: str = None
    ) -> Dict:
        """
        Generate content for Mon/Thu delivery with slider-based strategy
        
        Args:
            client_id: Client UUID
            opportunities: List of scored opportunities
            delivery_batch: e.g. 'MON-2025-W47'
            
        Returns:
            Generated content and stats
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🚀 Generating content for client: {client_id}")
        logger.info(f"{'='*70}\n")
        
        # STEP 1: Load client data
        client_response = self.supabase.table('clients').select('*').eq('client_id', client_id).single().execute()
        if not client_response.data:
            logger.error(f"❌ Client {client_id} not found")
            return {"success": False, "error": "Client not found"}
        
        client = client_response.data
        brand_name = client['company_name']
        
        # STEP 2: Load client settings WITH TIME-BASED PROGRESSION
        settings = self.strategy_progression.get_effective_strategy(client_id)
        
        logger.info(f"📊 Effective Strategy (Phase: {settings.get('phase_name', 'Unknown')}):")
        logger.info(f"   Days Active: {settings.get('days_since_onboarding', 0)}")
        logger.info(f"   Reply Percentage: {settings['reply_percentage']}%")
        logger.info(f"   Brand Mention: {settings['brand_mention_percentage']}%")
        logger.info(f"   Product Mention: {settings['product_mention_percentage']}%")
        if settings.get('phase_override_active'):
            logger.info(f"   ⚠️ PHASE OVERRIDE ACTIVE: Using {settings['current_phase']} settings")
        logger.info(f"   Special Instructions: {'✅ Present' if settings.get('explicit_instructions') else '❌ None'}\n")
        
        # STEP 3: Apply reply vs post ratio
        total_content = len(opportunities)
        reply_pct = settings['reply_percentage']
        num_replies = int(total_content * (reply_pct / 100))
        num_posts = total_content - num_replies
        
        logger.info(f"📝 Content Plan:")
        logger.info(f"   Total: {total_content} pieces")
        logger.info(f"   Replies: {num_replies}")
        logger.info(f"   Posts: {num_posts}\n")
        
        # STEP 3.5: Assign Reddit profiles to opportunities
        logger.info(f"🔄 Assigning Reddit profiles...")
        opportunities = self.profile_rotation.assign_profiles_to_opportunities(
            client_id,
            opportunities
        )
        logger.info(f"✅ Profile assignments complete\n")
        
        generated_content = []
        
        # STEP 4: Generate each piece of content
        for i, opportunity in enumerate(opportunities):
            try:
                # Determine content type
                content_type = 'reply' if i < num_replies else 'post'
                
                # STEP 5: Decide brand mention (applies to ALL content)
                mention_brand = self.should_mention_brand(settings['brand_mention_percentage'])
                
                # STEP 6: Decide product mention (only when similarity >= 75%)
                product_similarity = opportunity.get('product_similarity', 0)
                mention_product = self.should_mention_product(
                    settings['product_mention_percentage'],
                    product_similarity
                )
                
                logger.info(f"   Generating {content_type} #{i+1}:")
                logger.info(f"      Brand mention: {'✅ Yes' if mention_brand else '❌ No'}")
                logger.info(f"      Product mention: {'✅ Yes' if mention_product else '❌ No'} (similarity: {product_similarity:.2f})")
                
                # Get voice profile
                subreddit = opportunity.get('subreddit', '')  # Use correct column name
                voice_profile = self.get_voice_profile(subreddit, client_id)
                
                # Get product matches
                product_matches = opportunity.get('product_matchback')
                
                # CRITICAL: Get knowledge base insights for ALL posts (not just when products mentioned)
                # Use correct column names from opportunities table
                opportunity_text = f"{opportunity.get('thread_title', '')}\n\n{opportunity.get('original_post_text', '')}"
                knowledge_insights = self.knowledge_matchback.match_opportunity_to_knowledge(
                    opportunity_text=opportunity_text,
                    client_id=client_id,
                    similarity_threshold=0.50,  # Lowered from 0.70 to capture more knowledge matches
                    max_insights=3
                )
                scores = [f"{k['relevance_percentage']}%" for k in knowledge_insights]
                logger.info(f"      Knowledge insights found: {len(knowledge_insights)} (scores: {scores})")
                
                # STEP 7: Build prompt with special instructions AND ownership logic
                prompt, voice_params = self.build_generation_prompt(
                    opportunity=opportunity,
                    voice_profile=voice_profile,
                    product_matches=product_matches,
                    knowledge_insights=knowledge_insights,
                    client_settings=settings,
                    mention_brand=mention_brand,
                    mention_product=mention_product,
                    brand_name=brand_name,
                    client_data=client  # Pass client data for ownership check
                )

                # STEP 8: Generate with AI (with automatic retry and AI pattern detection)
                max_attempts = 3
                content_text = None
                ai_violations = []

                for attempt in range(max_attempts):
                    raw_content = self._call_openai_with_retry(prompt, max_tokens=350)

                    # Check for AI patterns
                    ai_violations = self.detect_ai_patterns(raw_content)

                    if not ai_violations:
                        content_text = raw_content
                        break
                    elif attempt < max_attempts - 1:
                        logger.warning(f"      ⚠️ AI patterns detected (attempt {attempt + 1}): {ai_violations[:3]}")
                        logger.info(f"      🔄 Regenerating content...")
                    else:
                        # Last attempt - use it anyway but log warning
                        logger.warning(f"      ⚠️ Using content with AI patterns after {max_attempts} attempts: {ai_violations[:3]}")
                        content_text = raw_content

                # STEP 8.5: Apply humanization post-processing
                if content_text:
                    # Apply lowercase sentence starts based on voice profile
                    lowercase_pct = voice_params.get('lowercase_pct', 15)
                    content_text = self.apply_lowercase_starts(content_text, lowercase_pct)

                    # Vary contractions based on voice profile
                    contraction_rate = voice_params.get('contraction_rate', 50)
                    content_text = self.vary_contractions(content_text, contraction_rate)

                    # Inject typos for casual subreddits
                    typo_count = voice_params.get('typo_count', 0)
                    if typo_count > 0:
                        content_text = self.inject_typos(content_text, typo_count)
                        logger.info(f"      📝 Injected {typo_count} typo(s) for casual tone")

                # STEP 8.6: Generate voice similarity proof
                voice_similarity_proof = self.generate_voice_similarity_proof(
                    voice_profile=voice_profile,
                    content=content_text,
                    subreddit=subreddit
                )
                logger.info(f"      🎤 Voice proof: {voice_similarity_proof[:50]}...")

                # STEP 8.7: TRACKING LINKS DISABLED - they get accounts banned
                # Links should NEVER be auto-appended to Reddit content
                # Traffic attribution moved to manual process
                pass
                
                # STEP 9: Log delivery to database WITH PROFILE INFO & KNOWLEDGE INSIGHTS
                db_error = self.log_content_delivery(
                    client_id=client_id,
                    content_type=content_type,
                    subreddit=subreddit,
                    content_text=content_text,
                    opportunity_id=opportunity.get('opportunity_id'),
                    reddit_item_id=opportunity.get('reddit_id'),
                    brand_mentioned=mention_brand,
                    product_mentioned=opportunity.get('matched_product') if mention_product else None,
                    delivery_batch=delivery_batch,
                    profile_id=opportunity.get('assigned_profile'),
                    profile_username=opportunity.get('profile_username'),
                    knowledge_insights_count=len(knowledge_insights)
                )

                # Extract voice profile data for export
                vp = voice_profile.get('voice_profile', voice_profile) if voice_profile else {}

                generated_content.append({
                    'type': content_type,
                    'text': content_text,
                    'subreddit': subreddit,
                    'brand_mentioned': mention_brand,
                    'product_mentioned': mention_product,
                    'knowledge_insights_used': len(knowledge_insights),
                    'knowledge_excerpts': [k.get('excerpt', '')[:100] for k in knowledge_insights[:2]] if knowledge_insights else [],
                    'assigned_profile': opportunity.get('profile_username', 'NO_PROFILE'),
                    'profile_karma': opportunity.get('profile_karma', 0),
                    'opportunity_id': opportunity.get('opportunity_id'),
                    'thread_title': opportunity.get('thread_title', ''),
                    'thread_url': opportunity.get('thread_url', ''),
                    'db_insert_error': db_error,  # Will be None if successful
                    # Voice matching data for Excel export
                    'voice_similarity_proof': voice_similarity_proof,
                    'formality_score': vp.get('formality_score', 0.5),
                    'tone': vp.get('dominant_tone') or vp.get('tone', 'conversational'),
                    'avg_word_count_target': vp.get('avg_word_count', 75),
                    'actual_word_count': len(content_text.split()) if content_text else 0,
                    'typos_injected': voice_params.get('typo_count', 0),
                    'ai_violations_detected': len(ai_violations),
                    'regeneration_attempts': max_attempts - (1 if not ai_violations else (max_attempts - ai_violations.count(ai_violations[0]) if ai_violations else max_attempts)),
                    'matched_keywords': opportunity.get('matched_keywords', ''),
                    'date_posted': opportunity.get('date_posted', ''),
                    'date_found': opportunity.get('date_found', ''),
                    'author_username': opportunity.get('author_username', ''),
                    'original_post_text': opportunity.get('original_post_text', '')[:500],
                })
                
            except Exception as e:
                import traceback
                error_tb = traceback.format_exc()
                logger.error(f"❌ Error generating content #{i+1}: {e}")
                logger.error(f"Traceback: {error_tb}")
                generated_content.append({
                    'type': 'error',
                    'error': str(e),
                    'traceback': error_tb,
                    'opportunity_id': opportunity.get('opportunity_id'),
                    'thread_title': opportunity.get('thread_title', '')
                })
                continue

        logger.info(f"\n✅ Generated {len(generated_content)} pieces of content")
        logger.info(f"{'='*70}\n")

        # Separate successful and error items
        successes = [c for c in generated_content if c.get('type') != 'error']
        errors = [c for c in generated_content if c.get('type') == 'error']

        return {
            "success": True,
            "generated": len(successes),
            "errors": len(errors),
            "content": successes,
            "error_details": errors[:3] if errors else []  # Include first 3 errors for debugging
        }
    
    def log_content_delivery(
        self,
        client_id: str,
        content_type: str,
        subreddit: str,
        content_text: str,
        opportunity_id: Optional[str],
        reddit_item_id: str,
        brand_mentioned: bool,
        product_mentioned: Optional[str],
        delivery_batch: Optional[str],
        profile_id: Optional[str] = None,
        profile_username: Optional[str] = None,
        knowledge_insights_count: int = 0
    ) -> Optional[str]:
        """Log content delivery to database for analytics WITH PROFILE INFO & KNOWLEDGE BASE USAGE

        Returns:
            None on success, error message string on failure
        """
        try:
            # Use column names that match actual Supabase schema
            # From reports_router.py: subreddit_name, delivered_at
            insert_data = {
                'client_id': client_id,
                'content_type': content_type,
                'subreddit_name': subreddit or 'unknown',
                'delivered_at': datetime.utcnow().isoformat(),
                'body': content_text,  # Body for the content
            }
            logger.info(f"      📝 Inserting to content_delivered: {list(insert_data.keys())}")
            result = self.supabase.table('content_delivered').insert(insert_data).execute()
            logger.info(f"      ✅ Logged {content_type} to content_delivered (result: {result.data})")
            return None
        except Exception as e:
            error_msg = str(e)
            logger.error(f"      ❌ Error logging delivery: {error_msg}")
            return error_msg

    def process_all_opportunities(
        self,
        client_id: Optional[str] = None,
        regenerate: bool = False,
        only_with_products: bool = False
    ) -> Dict:
        """
        Process all opportunities and generate content.
        Called by the scheduler pipeline.

        Args:
            client_id: Optional client ID to filter by
            regenerate: If True, regenerate existing content
            only_with_products: If True, only process opportunities with product matches

        Returns:
            Dictionary with processing results
        """
        try:
            logger.info("=" * 70)
            logger.info("🔥 PROCESS_ALL_OPPORTUNITIES CALLED")
            logger.info("=" * 70)
            logger.info(f"Client ID: {client_id}")
            logger.info(f"Regenerate: {regenerate}")
            logger.info(f"Only with products: {only_with_products}")

            # Build query for opportunities - get recent ones (simple query to avoid timeout)
            # The complex scoring filter was causing Supabase statement timeout
            logger.info("📊 Querying for recent opportunities (simple query)...")
            # Use correct column names: opportunity_id, thread_title, original_post_text, subreddit
            query = self.supabase.table("opportunities").select("opportunity_id, client_id, thread_title, original_post_text, subreddit, thread_url, date_found")
            if client_id:
                query = query.eq("client_id", client_id)
            query = query.order("date_found", desc=True)
            query = query.limit(10)  # Start with 10 to avoid timeout

            opportunities_response = query.execute()
            logger.info(f"📊 Query result: {len(opportunities_response.data or [])} opportunities found")

            if not opportunities_response.data:
                logger.info("No scored opportunities found to generate content for")
                return {
                    "success": True,
                    "processed": 0,
                    "with_product_mentions": 0,
                    "without_product_mentions": 0,
                    "message": "No opportunities to process"
                }

            opportunities = opportunities_response.data
            logger.info(f"Found {len(opportunities)} opportunities to generate content for")

            # Filter by product if required
            if only_with_products:
                opportunities = [o for o in opportunities if o.get('matched_product_id')]
                logger.info(f"Filtered to {len(opportunities)} opportunities with product matches")

                if not opportunities:
                    return {
                        "success": True,
                        "processed": 0,
                        "with_product_mentions": 0,
                        "without_product_mentions": 0,
                        "message": "No opportunities with product matches"
                    }

            # Check for existing content if not regenerating
            if not regenerate:
                existing_content = self.supabase.table("content_delivered")\
                    .select("opportunity_id")\
                    .in_("opportunity_id", [o["opportunity_id"] for o in opportunities])\
                    .execute()

                existing_ids = {c["opportunity_id"] for c in (existing_content.data or [])}
                opportunities = [o for o in opportunities if o["opportunity_id"] not in existing_ids]

                if not opportunities:
                    logger.info("All opportunities already have generated content")
                    return {
                        "success": True,
                        "processed": 0,
                        "with_product_mentions": 0,
                        "without_product_mentions": 0,
                        "message": "All opportunities already processed"
                    }

            # Group by client
            from collections import defaultdict
            by_client = defaultdict(list)
            for opp in opportunities:
                by_client[opp["client_id"]].append(opp)

            total_processed = 0
            with_products = 0
            without_products = 0

            # Generate content for each client's opportunities
            logger.info(f"🎯 Processing {len(by_client)} client(s) with opportunities")
            for cid, client_opps in by_client.items():
                logger.info("=" * 50)
                logger.info(f"🚀 CALLING generate_content_for_client")
                logger.info(f"   Client ID: {cid}")
                logger.info(f"   Opportunities: {len(client_opps)}")
                if client_opps:
                    sample = client_opps[0]
                    logger.info(f"   Sample opportunity keys: {list(sample.keys())[:10]}")
                    logger.info(f"   Sample opportunity ID: {sample.get('opportunity_id')}")

                try:
                    result = self.generate_content_for_client(
                        client_id=cid,
                        opportunities=client_opps,
                        delivery_batch=f"PIPELINE-{datetime.now().strftime('%Y-%m-%d')}"
                    )
                    logger.info(f"✅ generate_content_for_client returned: {result}")
                except Exception as gen_error:
                    logger.error(f"❌ generate_content_for_client FAILED: {gen_error}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    result = {"success": False, "error": str(gen_error)}

                if result.get("success"):
                    generated = result.get("generated", 0)
                    total_processed += generated

                    # Count product mentions
                    for content in result.get("content", []):
                        if content.get("product_mentioned"):
                            with_products += 1
                        else:
                            without_products += 1

            logger.info("=" * 70)
            logger.info(f"🏁 Content generation complete: {total_processed} pieces generated")
            logger.info("=" * 70)

            return {
                "success": True,
                "processed": total_processed,
                "with_product_mentions": with_products,
                "without_product_mentions": without_products
            }

        except Exception as e:
            import traceback
            logger.error("=" * 70)
            logger.error(f"❌ FATAL ERROR in process_all_opportunities: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error("=" * 70)
            return {
                "success": False,
                "error": str(e),
                "processed": 0,
                "with_product_mentions": 0,
                "without_product_mentions": 0
            }


# Standalone test function
def test_with_the_waite():
    """Test with The Waite client"""
    import asyncio
    
    THE_WAITE_CLIENT_ID = "466046c9-9e68-4957-8445-9a4fcf92def6"
    
    worker = ContentGenerationWorker()
    
    # Get some test opportunities
    opportunities_response = supabase.table('opportunities') \
        .select('*') \
        .eq('client_id', THE_WAITE_CLIENT_ID) \
        .limit(10) \
        .execute()
    
    if opportunities_response.data:
        result = worker.generate_content_for_client(
            client_id=THE_WAITE_CLIENT_ID,
            opportunities=opportunities_response.data,
            delivery_batch='TEST-2025-W47'
        )
        print(json.dumps(result, indent=2))
    else:
        print("No opportunities found for The Waite")


if __name__ == "__main__":
    test_with_the_waite()
