"""
Voice Database Worker - FULLY DYNAMIC VOICE PROFILE BUILDER

Crawls top Redditors in target subreddits to build comprehensive voice profiles.
ALL patterns are LEARNED from actual Reddit data - NO hardcoded word lists.

KEY PRINCIPLE: Compare subreddit vocabulary against baseline English to discover
what makes each community unique. This enables the system to learn slang, jargon,
and vocabulary patterns that don't exist yet or are specific to each community.

FIELDS EXTRACTED:
- Length patterns: avg_word_count, word_count_range, short_reply_probability
- Grammar patterns: capitalization_style, lowercase_start_pct
- Lexical patterns: common_phrases, unique_vocabulary (learned), signature_idioms
- Emoji patterns: emoji_frequency, common_emojis
- Tone patterns: dominant_tone, formality_score (calculated from patterns)
- Content patterns: example_openers, question_frequency, exclamation_usage_pct
- Raw data: sample_comments for reference

AUTO-REFRESH: Voice profiles should be refreshed every 30 days to stay current
with evolving community language patterns.
"""

import os
import asyncio
import logging
import re
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from collections import Counter
import math

import praw
import prawcore
from openai import OpenAI

from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

# ============================================================================
# BASELINE VOCABULARY - Common English words (not community-specific)
# This is loaded once and used to identify UNUSUAL words in each subreddit
# ============================================================================
BASELINE_VOCABULARY: Set[str] = set()


def _load_baseline_vocabulary() -> Set[str]:
    """
    Load baseline English vocabulary - the most common 5000 English words.
    Words appearing in the subreddit but NOT in this baseline are potentially
    unique/interesting vocabulary for that community.

    This is loaded once at module initialization.
    """
    global BASELINE_VOCABULARY

    if BASELINE_VOCABULARY:
        return BASELINE_VOCABULARY

    # Core English words - common in ALL contexts
    # This list covers the most frequent English words that appear everywhere
    # Any word NOT in this list that appears frequently in a subreddit is interesting
    common_words = {
        # Articles, pronouns, prepositions
        'the', 'a', 'an', 'and', 'or', 'but', 'if', 'then', 'because', 'as',
        'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into',
        'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from',
        'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again',
        'further', 'once', 'here', 'there', 'when', 'where', 'why', 'how',
        'all', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no',
        'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
        's', 't', 'can', 'will', 'just', 'don', 'should', 'now',

        # Common pronouns
        'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves',
        'you', 'your', 'yours', 'yourself', 'yourselves',
        'he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself',
        'it', 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves',
        'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those',
        'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing',
        'would', 'could', 'should', 'might', 'must', 'shall',

        # Common verbs
        'say', 'said', 'says', 'get', 'got', 'gets', 'getting',
        'make', 'made', 'makes', 'making', 'go', 'goes', 'went', 'going', 'gone',
        'know', 'knew', 'knows', 'knowing', 'known',
        'take', 'took', 'takes', 'taking', 'taken',
        'see', 'saw', 'sees', 'seeing', 'seen',
        'come', 'came', 'comes', 'coming',
        'think', 'thought', 'thinks', 'thinking',
        'look', 'looked', 'looks', 'looking',
        'want', 'wanted', 'wants', 'wanting',
        'give', 'gave', 'gives', 'giving', 'given',
        'use', 'used', 'uses', 'using',
        'find', 'found', 'finds', 'finding',
        'tell', 'told', 'tells', 'telling',
        'ask', 'asked', 'asks', 'asking',
        'work', 'worked', 'works', 'working',
        'seem', 'seemed', 'seems', 'seeming',
        'feel', 'felt', 'feels', 'feeling',
        'try', 'tried', 'tries', 'trying',
        'leave', 'left', 'leaves', 'leaving',
        'call', 'called', 'calls', 'calling',
        'keep', 'kept', 'keeps', 'keeping',
        'let', 'lets', 'letting',
        'begin', 'began', 'begins', 'beginning', 'begun',
        'help', 'helped', 'helps', 'helping',
        'show', 'showed', 'shows', 'showing', 'shown',
        'hear', 'heard', 'hears', 'hearing',
        'play', 'played', 'plays', 'playing',
        'run', 'ran', 'runs', 'running',
        'move', 'moved', 'moves', 'moving',
        'live', 'lived', 'lives', 'living',
        'believe', 'believed', 'believes', 'believing',
        'bring', 'brought', 'brings', 'bringing',
        'happen', 'happened', 'happens', 'happening',
        'write', 'wrote', 'writes', 'writing', 'written',
        'provide', 'provided', 'provides', 'providing',
        'sit', 'sat', 'sits', 'sitting',
        'stand', 'stood', 'stands', 'standing',
        'lose', 'lost', 'loses', 'losing',
        'pay', 'paid', 'pays', 'paying',
        'meet', 'met', 'meets', 'meeting',
        'include', 'included', 'includes', 'including',
        'continue', 'continued', 'continues', 'continuing',
        'set', 'sets', 'setting',
        'learn', 'learned', 'learns', 'learning',
        'change', 'changed', 'changes', 'changing',
        'lead', 'led', 'leads', 'leading',
        'understand', 'understood', 'understands', 'understanding',
        'watch', 'watched', 'watches', 'watching',
        'follow', 'followed', 'follows', 'following',
        'stop', 'stopped', 'stops', 'stopping',
        'create', 'created', 'creates', 'creating',
        'speak', 'spoke', 'speaks', 'speaking', 'spoken',
        'read', 'reads', 'reading',
        'allow', 'allowed', 'allows', 'allowing',
        'add', 'added', 'adds', 'adding',
        'spend', 'spent', 'spends', 'spending',
        'grow', 'grew', 'grows', 'growing', 'grown',
        'open', 'opened', 'opens', 'opening',
        'walk', 'walked', 'walks', 'walking',
        'win', 'won', 'wins', 'winning',
        'offer', 'offered', 'offers', 'offering',
        'remember', 'remembered', 'remembers', 'remembering',
        'consider', 'considered', 'considers', 'considering',
        'appear', 'appeared', 'appears', 'appearing',
        'buy', 'bought', 'buys', 'buying',
        'wait', 'waited', 'waits', 'waiting',
        'serve', 'served', 'serves', 'serving',
        'die', 'died', 'dies', 'dying',
        'send', 'sent', 'sends', 'sending',
        'expect', 'expected', 'expects', 'expecting',
        'build', 'built', 'builds', 'building',
        'stay', 'stayed', 'stays', 'staying',
        'fall', 'fell', 'falls', 'falling', 'fallen',
        'cut', 'cuts', 'cutting',
        'reach', 'reached', 'reaches', 'reaching',
        'kill', 'killed', 'kills', 'killing',
        'remain', 'remained', 'remains', 'remaining',

        # Common adjectives
        'good', 'new', 'first', 'last', 'long', 'great', 'little', 'own',
        'old', 'right', 'big', 'high', 'different', 'small', 'large',
        'next', 'early', 'young', 'important', 'few', 'public', 'bad',
        'same', 'able', 'better', 'best', 'sure', 'free', 'true', 'real',

        # Common nouns
        'time', 'year', 'people', 'way', 'day', 'man', 'thing', 'woman',
        'life', 'child', 'world', 'school', 'state', 'family', 'student',
        'group', 'country', 'problem', 'hand', 'part', 'place', 'case',
        'week', 'company', 'system', 'program', 'question', 'work',
        'government', 'number', 'night', 'point', 'home', 'water', 'room',
        'mother', 'area', 'money', 'story', 'fact', 'month', 'lot', 'right',
        'study', 'book', 'eye', 'job', 'word', 'business', 'issue', 'side',
        'kind', 'head', 'house', 'service', 'friend', 'father', 'power',
        'hour', 'game', 'line', 'end', 'member', 'law', 'car', 'city',
        'community', 'name', 'president', 'team', 'minute', 'idea', 'kid',
        'body', 'information', 'back', 'parent', 'face', 'others', 'level',
        'office', 'door', 'health', 'person', 'art', 'war', 'history',
        'party', 'result', 'change', 'morning', 'reason', 'research', 'girl',
        'guy', 'moment', 'air', 'teacher', 'force', 'education',

        # Common adverbs
        'also', 'well', 'even', 'back', 'still', 'already', 'always',
        'never', 'often', 'ever', 'really', 'maybe', 'probably', 'actually',
        'usually', 'sometimes', 'almost', 'enough', 'especially', 'ago',
        'away', 'today', 'far', 'together', 'yet', 'soon', 'later',
        'certainly', 'clearly', 'however', 'perhaps', 'likely', 'simply',
        'generally', 'instead', 'indeed',

        # Question words and common conjunctions
        'whether', 'while', 'although', 'though', 'since', 'unless',
        'until', 'within', 'without', 'according', 'either', 'neither',
        'both', 'rather', 'anything', 'everything', 'something', 'nothing',
        'anyone', 'everyone', 'someone', 'nobody',

        # Numbers as words
        'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight',
        'nine', 'ten', 'hundred', 'thousand', 'million',

        # Internet/Reddit common (these are baseline, not unique)
        'post', 'comment', 'thread', 'edit', 'update', 'reddit', 'sub',
        'subreddit', 'op', 'link', 'source', 'thanks', 'thank', 'sorry',
        'yes', 'no', 'yeah', 'nope', 'okay', 'ok', 'please', 'like',
        'literally', 'basically', 'totally', 'definitely', 'exactly',
        'honestly', 'seriously', 'obviously', 'apparently',
    }

    BASELINE_VOCABULARY = common_words
    logger.info(f"Loaded baseline vocabulary: {len(BASELINE_VOCABULARY)} common English words")
    return BASELINE_VOCABULARY


# Initialize baseline on module load
_load_baseline_vocabulary()


class VoiceDatabaseWorker:
    """
    Fully dynamic voice profile builder.
    Crawls subreddit users and extracts ACTUAL writing patterns.
    NO hardcoded slang or formality lists - everything is LEARNED.
    """

    def __init__(self):
        self.supabase = get_supabase_client()
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Initialize Reddit API
        self.reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0")
        )

        # Configurable crawl settings
        self.TOP_USERS_PER_SUBREDDIT = 100  # Default, can be overridden
        self.COMMENTS_PER_USER = 20
        self.MIN_COMMENT_LENGTH = 20

        # Voice profile refresh interval (30 days)
        self.PROFILE_REFRESH_DAYS = 30

    async def analyze_subreddit_voice(
        self,
        subreddit_name: str,
        client_id: str,
        user_limit: Optional[int] = None,
        comments_per_user: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Build comprehensive voice profile for a subreddit.

        Args:
            subreddit_name: Name of subreddit (e.g., "HomeImprovement")
            client_id: UUID of client
            user_limit: Override default user limit
            comments_per_user: Override default comments per user

        Returns:
            Complete voice profile dictionary
        """
        try:
            user_limit = user_limit or self.TOP_USERS_PER_SUBREDDIT
            comments_per_user = comments_per_user or self.COMMENTS_PER_USER

            logger.info(f"🎤 Building voice profile for r/{subreddit_name} (users: {user_limit}, comments/user: {comments_per_user})")

            # Step 1: Get top active users in subreddit
            top_users = await self._get_top_subreddit_users(subreddit_name, limit=user_limit)
            logger.info(f"📊 Found {len(top_users)} active users in r/{subreddit_name}")

            if not top_users:
                logger.warning(f"No users found in r/{subreddit_name} - using default profile")
                return self._get_default_voice_profile(subreddit_name)

            # Step 2: Collect comments from these users
            all_comments = []
            users_processed = 0
            for user in top_users[:user_limit]:
                try:
                    comments = await self._get_user_comments_in_subreddit(
                        user['username'],
                        subreddit_name,
                        limit=comments_per_user
                    )
                    if comments:
                        all_comments.extend(comments)
                        users_processed += 1
                except Exception as e:
                    logger.warning(f"Failed to get comments for u/{user['username']}: {e}")
                    continue

            logger.info(f"📝 Collected {len(all_comments)} comments from {users_processed} users in r/{subreddit_name}")

            if len(all_comments) < 50:
                logger.warning(f"Insufficient comments ({len(all_comments)}) - augmenting with default values")

            # Step 3: Analyze ALL patterns from comments
            profile = self._analyze_comprehensive_patterns(all_comments, subreddit_name)
            profile['users_analyzed'] = users_processed
            profile['comments_analyzed'] = len(all_comments)
            profile['last_crawl_date'] = datetime.utcnow().isoformat()

            # Step 4: Enhance with AI analysis for tone/sentiment
            profile = await self._enhance_with_ai_analysis(profile, all_comments[:30])

            # Step 5: Save to database
            await self._save_voice_profile(subreddit_name, client_id, profile)

            logger.info(f"✅ Voice profile complete for r/{subreddit_name}: {len(all_comments)} comments analyzed")
            return profile

        except Exception as e:
            logger.error(f"❌ Error building voice profile for r/{subreddit_name}: {e}")
            raise

    async def _get_top_subreddit_users(self, subreddit_name: str, limit: int = 100) -> List[Dict]:
        """Get top active users from subreddit hot/top posts"""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            user_karma = Counter()

            # Sample from hot, top, and new posts
            post_sources = [
                ('hot', subreddit.hot(limit=50)),
                ('top', subreddit.top(limit=30, time_filter='month')),
                ('new', subreddit.new(limit=20))
            ]

            for source_name, submissions in post_sources:
                for submission in submissions:
                    try:
                        submission.comments.replace_more(limit=0)
                        for comment in submission.comments.list()[:30]:
                            if hasattr(comment, 'author') and comment.author:
                                # Skip bots and AutoModerator
                                username = comment.author.name
                                if username.lower() not in ['automoderator', 'reddit']:
                                    user_karma[username] += comment.score
                    except Exception:
                        continue

            # Convert to sorted list
            top_users = [
                {'username': username, 'karma': karma}
                for username, karma in user_karma.most_common(limit)
                if karma > 0  # Only users with positive karma
            ]

            return top_users

        except Exception as e:
            logger.error(f"Error getting top users from r/{subreddit_name}: {e}")
            return []

    async def _get_user_comments_in_subreddit(
        self,
        username: str,
        subreddit_name: str,
        limit: int = 20
    ) -> List[Dict]:
        """Get recent comments from user in specific subreddit"""
        try:
            user = self.reddit.redditor(username)
            comments = []

            for comment in user.comments.new(limit=limit * 3):  # Get more to filter
                try:
                    if hasattr(comment, 'subreddit'):
                        if comment.subreddit.display_name.lower() == subreddit_name.lower():
                            body = comment.body
                            if len(body) >= self.MIN_COMMENT_LENGTH and body not in ['[deleted]', '[removed]']:
                                comments.append({
                                    'body': body,
                                    'score': comment.score,
                                    'created_utc': comment.created_utc
                                })
                                if len(comments) >= limit:
                                    break
                except Exception:
                    continue

            return comments

        except prawcore.exceptions.NotFound:
            logger.debug(f"User {username} not found or deleted")
            return []
        except prawcore.exceptions.Forbidden:
            logger.debug(f"User {username} has private profile")
            return []
        except Exception as e:
            logger.warning(f"Error getting comments for u/{username}: {e}")
            return []

    def _discover_unique_vocabulary(self, word_counts: Counter, min_frequency: int = 3) -> Dict[str, Any]:
        """
        Discover vocabulary unique to this subreddit by comparing against baseline English.

        This is the KEY to learning - we find words that appear frequently in this
        subreddit but are NOT common English words. These represent:
        - Community slang (ngl, tbh, etc.)
        - Industry jargon (HVAC terms, crypto terms, etc.)
        - Subreddit-specific memes or phrases
        - Technical vocabulary

        Args:
            word_counts: Counter of all words found in comments
            min_frequency: Minimum times a word must appear to be considered

        Returns:
            Dictionary containing unique_vocabulary list and analysis
        """
        global BASELINE_VOCABULARY

        unique_words = []
        abbreviations = []  # Short words that might be acronyms/slang
        technical_terms = []  # Longer unusual words

        for word, count in word_counts.most_common(500):
            if count < min_frequency:
                continue

            # Skip very short words and numbers
            if len(word) < 2 or word.isdigit():
                continue

            # Check if NOT in baseline vocabulary
            if word not in BASELINE_VOCABULARY:
                # Categorize the unique word
                word_info = {
                    "word": word,
                    "frequency": count,
                    "per_thousand": round(count / sum(word_counts.values()) * 1000, 2)
                }

                if len(word) <= 4 and word.isalpha():
                    # Short word - likely abbreviation/slang (lol, tbh, ngl, hvac)
                    abbreviations.append(word_info)
                elif not word.isalpha():
                    # Contains numbers or special chars - technical (401k, a/c, etc.)
                    technical_terms.append(word_info)
                else:
                    # Regular unique word
                    unique_words.append(word_info)

        # Sort by frequency
        abbreviations.sort(key=lambda x: x['frequency'], reverse=True)
        technical_terms.sort(key=lambda x: x['frequency'], reverse=True)
        unique_words.sort(key=lambda x: x['frequency'], reverse=True)

        # Combine into single list for backwards compatibility
        all_unique = abbreviations + unique_words + technical_terms

        return {
            "unique_vocabulary": [w['word'] for w in all_unique[:30]],
            "abbreviations_slang": [w['word'] for w in abbreviations[:15]],
            "technical_terms": [w['word'] for w in technical_terms[:10]],
            "vocabulary_richness": len(all_unique),
            "top_unique_with_freq": all_unique[:20]
        }

    def _calculate_dynamic_formality(
        self,
        all_words: List[str],
        word_counts: Counter,
        avg_word_length: float,
        lowercase_start_pct: float,
        contraction_rate: float,
        exclamation_pct: float
    ) -> Dict[str, Any]:
        """
        Calculate formality score from ACTUAL patterns, not predefined word lists.

        Formality indicators derived from linguistic research:
        - Average word length (formal writing uses longer words)
        - Sentence-initial capitalization (formal = proper caps)
        - Contraction usage (formal = fewer contractions)
        - Exclamation usage (formal = fewer exclamations)
        - First-person pronoun frequency (formal = fewer I/me/my)

        Returns score 0-1 where 0 = very casual, 1 = very formal
        """
        scores = []

        # 1. Word length score (casual ~4 chars, formal ~6+ chars)
        # Scale: 3.5 chars = 0, 6.5 chars = 1
        word_length_score = max(0, min(1, (avg_word_length - 3.5) / 3.0))
        scores.append(('word_length', word_length_score, 0.25))

        # 2. Capitalization score (lowercase starts = casual)
        # 0% lowercase = formal (1.0), 60%+ lowercase = casual (0)
        cap_score = max(0, 1 - (lowercase_start_pct / 60))
        scores.append(('capitalization', cap_score, 0.20))

        # 3. Contraction score (more contractions = more casual)
        # 0% contractions = formal (1.0), 10%+ = casual (0)
        contraction_score = max(0, 1 - (contraction_rate / 10))
        scores.append(('contractions', contraction_score, 0.20))

        # 4. Exclamation score (more exclamations = more casual)
        # 0% exclamations = formal (1.0), 15%+ = casual (0)
        exclamation_score = max(0, 1 - (exclamation_pct / 15))
        scores.append(('exclamations', exclamation_score, 0.15))

        # 5. First-person pronoun frequency (I, me, my)
        total_words = sum(word_counts.values()) if word_counts else 1
        first_person = sum(word_counts.get(p, 0) for p in ['i', 'me', 'my', 'myself'])
        first_person_rate = (first_person / total_words) * 100
        # 0% first-person = formal (1.0), 10%+ = casual (0)
        pronoun_score = max(0, 1 - (first_person_rate / 10))
        scores.append(('first_person', pronoun_score, 0.20))

        # Weighted average
        weighted_sum = sum(score * weight for _, score, weight in scores)
        total_weight = sum(weight for _, _, weight in scores)
        formality_score = weighted_sum / total_weight if total_weight > 0 else 0.35

        # Determine formality level label
        if formality_score >= 0.7:
            formality_level = "HIGH"
        elif formality_score >= 0.4:
            formality_level = "MEDIUM"
        else:
            formality_level = "LOW"

        return {
            "formality_score": round(formality_score, 2),
            "formality_level": formality_level,
            "formality_breakdown": {
                name: round(score, 2) for name, score, _ in scores
            }
        }

    def _count_contractions(self, all_words: List[str]) -> int:
        """Count contracted words in the word list"""
        # Common contraction patterns
        contraction_patterns = [
            "n't", "'s", "'re", "'ve", "'ll", "'d", "'m",
            "nt", "dont", "wont", "cant", "shouldnt", "wouldnt", "couldnt",
            "isnt", "arent", "wasnt", "werent", "hasnt", "havent", "hadnt",
            "didnt", "doesnt", "im", "youre", "theyre", "weve", "theyve",
            "ive", "youve", "itll", "theyll", "youll", "well", "shell",
            "hed", "shed", "theyd", "youd", "wed", "id"
        ]
        count = 0
        for word in all_words:
            word_lower = word.lower()
            if any(pattern in word_lower for pattern in ["'", "'"]):
                count += 1
            elif word_lower in contraction_patterns:
                count += 1
        return count

    def _analyze_comprehensive_patterns(self, comments: List[Dict], subreddit_name: str) -> Dict[str, Any]:
        """
        Analyze ALL linguistic patterns from comments.
        This is where the actual LEARNING happens - FULLY DYNAMIC, no hardcoded lists.
        """
        if not comments:
            return self._get_default_voice_profile(subreddit_name)

        # Initialize counters
        word_counts_list = []
        sentence_counts = []
        lowercase_starts = 0
        total_sentences = 0
        exclamation_count = 0
        question_count = 0
        total_comments = len(comments)
        total_word_length = 0
        total_word_count = 0

        # Word/phrase tracking
        all_words = []
        word_counter = Counter()
        bigrams = []
        trigrams = []
        openers = []
        closers = []
        emojis_found = []

        # Process each comment
        for comment_data in comments:
            text = comment_data.get('body', '')
            if not text or text in ['[deleted]', '[removed]']:
                continue

            # Word count
            words = text.split()
            word_counts_list.append(len(words))

            for w in words:
                clean_word = w.lower().strip('.,!?;:"\'()[]{}')
                if clean_word:
                    all_words.append(clean_word)
                    word_counter[clean_word] += 1
                    total_word_length += len(clean_word)
                    total_word_count += 1

            # Sentence analysis
            sentences = self._split_into_sentences(text)
            sentence_counts.append(len(sentences))

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                total_sentences += 1

                # Check lowercase start (excluding quotes and formatting)
                first_char = sentence[0] if sentence else ''
                if first_char.isalpha() and first_char.islower():
                    lowercase_starts += 1

                # Punctuation analysis
                if sentence.endswith('!'):
                    exclamation_count += 1
                if sentence.endswith('?'):
                    question_count += 1

            # Extract opener (first 3 words)
            if len(words) >= 3:
                opener = ' '.join(words[:3]).lower()
                opener = re.sub(r'[^\w\s]', '', opener)
                if opener:
                    openers.append(opener)

            # Extract closer (last 3 words)
            if len(words) >= 3:
                closer = ' '.join(words[-3:]).lower()
                closer = re.sub(r'[^\w\s]', '', closer)
                if closer:
                    closers.append(closer)

            # Find emojis
            emojis_in_text = self._extract_emojis(text)
            emojis_found.extend(emojis_in_text)

            # Build bigrams and trigrams
            clean_words = [w.lower().strip('.,!?;:') for w in words if w.isalpha() or w.isalnum()]
            if len(clean_words) >= 2:
                bigrams.extend([f"{clean_words[i]} {clean_words[i+1]}" for i in range(len(clean_words)-1)])
            if len(clean_words) >= 3:
                trigrams.extend([f"{clean_words[i]} {clean_words[i+1]} {clean_words[i+2]}" for i in range(len(clean_words)-2)])

        # === CALCULATE STATISTICS ===

        # Word count statistics
        avg_word_count = sum(word_counts_list) / len(word_counts_list) if word_counts_list else 50
        sorted_counts = sorted(word_counts_list)

        if len(sorted_counts) >= 10:
            p10_idx = len(sorted_counts) // 10
            p90_idx = len(sorted_counts) * 9 // 10
            word_count_range = {"min": sorted_counts[p10_idx], "max": sorted_counts[p90_idx]}
        else:
            word_count_range = {
                "min": min(word_counts_list) if word_counts_list else 20,
                "max": max(word_counts_list) if word_counts_list else 150
            }

        # Short reply probability (under 50 words)
        short_replies = sum(1 for wc in word_counts_list if wc < 50)
        short_reply_probability = short_replies / len(word_counts_list) if word_counts_list else 0.5

        # Capitalization analysis
        lowercase_start_pct = (lowercase_starts / total_sentences * 100) if total_sentences > 0 else 20
        if lowercase_start_pct > 60:
            capitalization_style = "mostly_lowercase"
        elif lowercase_start_pct > 30:
            capitalization_style = "mixed"
        else:
            capitalization_style = "proper"

        # Exclamation and question frequency
        exclamation_usage_pct = (exclamation_count / total_sentences * 100) if total_sentences > 0 else 5
        question_frequency = question_count / total_comments if total_comments > 0 else 0.1

        # Common phrases
        common_phrases = self._find_common_phrases(bigrams, trigrams, min_count=3)

        # ====== DYNAMIC VOCABULARY DISCOVERY ======
        # This replaces the old hardcoded slang detection
        vocab_analysis = self._discover_unique_vocabulary(word_counter, min_frequency=3)
        unique_vocabulary = vocab_analysis['unique_vocabulary']
        abbreviations_slang = vocab_analysis['abbreviations_slang']

        # Signature idioms (subreddit-specific)
        signature_idioms = self._find_signature_idioms(trigrams, min_count=3)

        # Emoji analysis
        emoji_counts = Counter(emojis_found)
        common_emojis = [emoji for emoji, count in emoji_counts.most_common(5) if count >= 2]
        comments_with_emojis = sum(1 for c in comments if self._extract_emojis(c.get('body', '')))
        emoji_ratio = comments_with_emojis / total_comments if total_comments > 0 else 0

        if emoji_ratio > 0.3:
            emoji_frequency = "frequent"
        elif emoji_ratio > 0.1:
            emoji_frequency = "occasional"
        elif emoji_ratio > 0.02:
            emoji_frequency = "rare"
        else:
            emoji_frequency = "none"

        # Opener analysis
        opener_counts = Counter(openers)
        example_openers = [op for op, count in opener_counts.most_common(8) if count >= 2]

        # Closer analysis
        closer_counts = Counter(closers)
        example_closers = [cl for cl, count in closer_counts.most_common(5) if count >= 2]

        # ====== DYNAMIC FORMALITY CALCULATION ======
        # This replaces the old hardcoded formality indicators
        avg_word_length = total_word_length / total_word_count if total_word_count > 0 else 4.5
        contraction_count = self._count_contractions(all_words)
        contraction_rate = (contraction_count / total_word_count * 100) if total_word_count > 0 else 5

        formality_analysis = self._calculate_dynamic_formality(
            all_words=all_words,
            word_counts=word_counter,
            avg_word_length=avg_word_length,
            lowercase_start_pct=lowercase_start_pct,
            contraction_rate=contraction_rate,
            exclamation_pct=exclamation_usage_pct
        )

        # Hedging frequency ("I think", "maybe", "probably")
        hedging_words = ['think', 'maybe', 'probably', 'might', 'perhaps', 'possibly', 'guess', 'suppose']
        hedging_count = sum(1 for w in all_words if w in hedging_words)
        hedging_frequency = hedging_count / len(all_words) if all_words else 0.02

        # Sample comments (top scored for reference)
        sample_comments = [
            {"text": c.get('body', '')[:400], "score": c.get('score', 0)}
            for c in sorted(comments, key=lambda x: x.get('score', 0), reverse=True)[:5]
        ]

        return {
            "subreddit": subreddit_name,

            # Length patterns
            "avg_word_count": round(avg_word_count, 1),
            "word_count_range": word_count_range,
            "short_reply_probability": round(short_reply_probability, 2),
            "avg_word_length": round(avg_word_length, 2),

            # Grammar patterns
            "capitalization_style": capitalization_style,
            "lowercase_start_pct": round(lowercase_start_pct, 1),
            "contraction_rate": round(contraction_rate, 2),

            # Lexical patterns - NOW FULLY DYNAMIC
            "common_phrases": common_phrases[:15],
            "unique_vocabulary": unique_vocabulary[:20],  # Replaces slang_examples
            "abbreviations_slang": abbreviations_slang[:15],  # Learned abbreviations
            "signature_idioms": signature_idioms[:8],
            "vocabulary_richness": vocab_analysis['vocabulary_richness'],

            # Emoji patterns
            "emoji_frequency": emoji_frequency,
            "common_emojis": common_emojis,

            # Content patterns
            "example_openers": example_openers[:5],
            "example_closers": example_closers[:5],
            "question_frequency": round(question_frequency, 2),
            "exclamation_usage_pct": round(exclamation_usage_pct, 1),
            "hedging_frequency": round(hedging_frequency, 3),

            # Tone patterns - NOW DYNAMICALLY CALCULATED
            "formality_score": formality_analysis['formality_score'],
            "formality_level": formality_analysis['formality_level'],
            "formality_breakdown": formality_analysis['formality_breakdown'],
            "dominant_tone": "helpful",  # Default, AI will refine

            # Raw data
            "sample_comments": sample_comments,

            # Learning metadata
            "learning_method": "dynamic_vocabulary_discovery",
            "baseline_vocabulary_size": len(BASELINE_VOCABULARY)
        }

    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Handle common abbreviations
        text = re.sub(r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e)\.\s', r'\1<DOT> ', text)
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.replace('<DOT>', '.').strip() for s in sentences if s.strip()]
        return sentences

    def _extract_emojis(self, text: str) -> List[str]:
        """Extract emojis from text"""
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F700-\U0001F77F"  # alchemical symbols
            "\U0001F780-\U0001F7FF"  # Geometric Shapes
            "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
            "\U0001F900-\U0001F9FF"  # Supplemental Symbols
            "\U0001FA00-\U0001FA6F"  # Chess Symbols
            "\U0001FA70-\U0001FAFF"  # Symbols Extended-A
            "\U00002702-\U000027B0"  # Dingbats
            "\U0001F1E0-\U0001F1FF"  # Flags
            "]+"
        )
        return emoji_pattern.findall(text)

    def _find_common_phrases(self, bigrams: List[str], trigrams: List[str], min_count: int = 3) -> List[str]:
        """Find commonly used phrases, filtering stop words"""
        stop_patterns = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'and', 'or', 'in', 'on', 'at', 'it', 'i', 'you', 'he', 'she', 'they', 'we', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'for', 'with', 'as', 'by', 'from', 'but', 'not', 'if', 'so', 'my', 'your', 'his', 'her', 'its', 'our', 'their', 'what', 'which', 'who', 'when', 'where', 'how', 'why', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'only', 'own', 'same', 'than', 'too', 'very', 'just', 'also'}

        bigram_counts = Counter(bigrams)
        trigram_counts = Counter(trigrams)

        common = []

        # Prefer trigrams
        for phrase, count in trigram_counts.most_common(50):
            if count >= min_count:
                words = set(phrase.split())
                # At least one non-stop word
                if not words.issubset(stop_patterns):
                    common.append(phrase)

        # Add unique bigrams
        for phrase, count in bigram_counts.most_common(50):
            if count >= min_count and phrase not in common:
                words = set(phrase.split())
                if not words.issubset(stop_patterns):
                    common.append(phrase)

        return common[:15]

    def _find_signature_idioms(self, trigrams: List[str], min_count: int = 3) -> List[str]:
        """Find phrases that might be specific to this subreddit"""
        trigram_counts = Counter(trigrams)
        return [phrase for phrase, count in trigram_counts.most_common(10) if count >= min_count]

    async def _enhance_with_ai_analysis(self, basic_profile: Dict, sample_comments: List[Dict]) -> Dict[str, Any]:
        """Use GPT-4 to extract nuanced tone, sentiment, and style insights"""
        if not sample_comments:
            return basic_profile

        sample_text = "\n\n---\n\n".join([c.get('body', '')[:300] for c in sample_comments[:15]])

        try:
            response = self.openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a linguistic analyst. Analyze Reddit comments and return JSON only."
                    },
                    {
                        "role": "user",
                        "content": f"""Analyze these comments from r/{basic_profile['subreddit']}:

{sample_text}

Return a JSON object with ONLY these fields:
{{
    "tone": "3-5 word description of emotional tone",
    "grammar_style": "brief description of grammar patterns",
    "sentiment_distribution": {{"supportive": 40, "neutral": 30, "critical": 20, "other": 10}},
    "formality_level": "LOW or MEDIUM or HIGH",
    "voice_description": "2 sentences describing how this community writes"
}}

Return ONLY valid JSON, no other text."""
                    }
                ],
                temperature=0.3,
                max_tokens=300
            )

            import json
            ai_analysis = json.loads(response.choices[0].message.content)

            # Merge AI analysis with basic profile
            basic_profile['tone'] = ai_analysis.get('tone', 'helpful, casual')
            basic_profile['grammar_style'] = ai_analysis.get('grammar_style', 'conversational')
            basic_profile['sentiment_distribution'] = ai_analysis.get('sentiment_distribution', {})
            basic_profile['formality_level'] = ai_analysis.get('formality_level', 'LOW')
            basic_profile['voice_description'] = ai_analysis.get('voice_description', '')

            # Update dominant_tone based on AI analysis
            if 'tone' in ai_analysis:
                basic_profile['dominant_tone'] = ai_analysis['tone']

            return basic_profile

        except Exception as e:
            logger.warning(f"AI analysis failed, using defaults: {e}")
            # Return profile with default values
            basic_profile['tone'] = 'supportive, casual'
            basic_profile['grammar_style'] = 'conversational with informal patterns'
            basic_profile['sentiment_distribution'] = {"supportive": 50, "neutral": 30, "critical": 20}
            basic_profile['formality_level'] = 'LOW'
            basic_profile['voice_description'] = f"r/{basic_profile['subreddit']} users write casually and helpfully."
            return basic_profile

    def _get_default_voice_profile(self, subreddit_name: str) -> Dict[str, Any]:
        """Return default voice profile when crawling fails"""
        return {
            "subreddit": subreddit_name,

            # Length patterns
            "avg_word_count": 75,
            "word_count_range": {"min": 30, "max": 200},
            "short_reply_probability": 0.4,
            "avg_word_length": 4.5,

            # Grammar patterns
            "capitalization_style": "mixed",
            "lowercase_start_pct": 25,
            "contraction_rate": 5.0,

            # Lexical patterns - DYNAMIC (empty by default)
            "common_phrases": ["honestly", "in my experience", "i think", "typically"],
            "unique_vocabulary": [],  # Will be learned
            "abbreviations_slang": [],  # Will be learned
            "signature_idioms": [],
            "vocabulary_richness": 0,

            # Emoji patterns
            "emoji_frequency": "rare",
            "common_emojis": [],

            # Content patterns
            "example_openers": [],
            "example_closers": [],
            "question_frequency": 0.15,
            "exclamation_usage_pct": 8,
            "hedging_frequency": 0.02,

            # Tone patterns - DYNAMICALLY CALCULATED
            "formality_score": 0.35,
            "formality_level": "LOW",
            "formality_breakdown": {
                "word_length": 0.33,
                "capitalization": 0.58,
                "contractions": 0.50,
                "exclamations": 0.47,
                "first_person": 0.20
            },
            "dominant_tone": "helpful, casual",
            "tone": "supportive, conversational",
            "grammar_style": "casual with informal patterns",
            "sentiment_distribution": {"supportive": 50, "neutral": 30, "critical": 20},
            "voice_description": "Default Reddit community voice. Friendly and authentic.",

            # Raw data
            "sample_comments": [],

            # Metadata
            "users_analyzed": 0,
            "comments_analyzed": 0,
            "is_fallback": True,
            "last_crawl_date": datetime.utcnow().isoformat(),
            "learning_method": "default_fallback",
            "baseline_vocabulary_size": len(BASELINE_VOCABULARY)
        }

    async def _save_voice_profile(self, subreddit_name: str, client_id: str, profile: Dict) -> None:
        """Save voice profile to database with ALL fields"""
        try:
            subreddit_lower = subreddit_name.lower()

            # Build complete record
            data = {
                "client_id": client_id,
                "subreddit": subreddit_lower,
                "redditor_username": f"__subreddit_voice_{subreddit_lower}__",

                # Store complete profile as JSONB
                "voice_profile": profile,

                # Also store key fields as columns for easier querying
                "dominant_tone": profile.get('dominant_tone', 'helpful'),
                "formality_score": profile.get('formality_score', 0.35),
                "lowercase_start_pct": profile.get('lowercase_start_pct', 25),
                "exclamation_usage_pct": profile.get('exclamation_usage_pct', 8),

                # Metadata
                "users_analyzed": profile.get('users_analyzed', 0),
                "comments_analyzed": profile.get('comments_analyzed', 0),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            # Delete existing profile for this client/subreddit
            try:
                self.supabase.table("voice_profiles")\
                    .delete()\
                    .eq("client_id", client_id)\
                    .eq("subreddit", subreddit_lower)\
                    .execute()
            except Exception:
                pass

            # Insert new profile
            self.supabase.table("voice_profiles").insert(data).execute()
            logger.info(f"✅ Saved voice profile for r/{subreddit_name}: {profile.get('comments_analyzed', 0)} comments analyzed")

        except Exception as e:
            logger.error(f"Error saving voice profile for r/{subreddit_name}: {e}")
            raise


async def build_client_voice_database(client_id: str, user_limit: int = 100, comments_per_user: int = 20) -> Dict[str, Any]:
    """
    Build complete voice database for a client's target subreddits.

    Args:
        client_id: UUID of client
        user_limit: Users to analyze per subreddit
        comments_per_user: Comments to collect per user

    Returns:
        Summary of voice profiles created
    """
    worker = VoiceDatabaseWorker()
    worker.TOP_USERS_PER_SUBREDDIT = user_limit
    worker.COMMENTS_PER_USER = comments_per_user

    supabase = get_supabase_client()

    # Get subreddits from client_subreddit_config
    subreddits_response = supabase.table("client_subreddit_config")\
        .select("subreddit_name")\
        .eq("client_id", client_id)\
        .eq("is_active", True)\
        .execute()

    subreddits = [s['subreddit_name'] for s in subreddits_response.data] if subreddits_response.data else []

    # Fallback: Get unique subreddits from opportunities
    if not subreddits:
        logger.info("No subreddit config found, checking opportunities table")
        opps_response = supabase.table("opportunities")\
            .select("subreddit")\
            .eq("client_id", client_id)\
            .execute()
        if opps_response.data:
            subreddits = list(set([o['subreddit'] for o in opps_response.data if o.get('subreddit')]))[:10]
            logger.info(f"Found {len(subreddits)} unique subreddits from opportunities")

    if not subreddits:
        return {
            "client_id": client_id,
            "total_subreddits": 0,
            "successful": 0,
            "failed": 0,
            "results": [],
            "message": "No subreddits configured for this client"
        }

    logger.info(f"🎤 Building voice database for {len(subreddits)} subreddits")

    results = []
    for subreddit in subreddits:
        try:
            profile = await worker.analyze_subreddit_voice(
                subreddit,
                client_id,
                user_limit=user_limit,
                comments_per_user=comments_per_user
            )
            results.append({
                "subreddit": subreddit,
                "status": "success",
                "comments_analyzed": profile.get('comments_analyzed', 0),
                "users_analyzed": profile.get('users_analyzed', 0)
            })
        except Exception as e:
            logger.error(f"Failed to build voice profile for r/{subreddit}: {e}")
            results.append({
                "subreddit": subreddit,
                "status": "failed",
                "error": str(e)
            })

    return {
        "client_id": client_id,
        "total_subreddits": len(subreddits),
        "successful": sum(1 for r in results if r['status'] == 'success'),
        "failed": sum(1 for r in results if r['status'] == 'failed'),
        "results": results
    }


# ============================================================================
# VOICE PROFILE FRESHNESS & AUTO-REFRESH
# ============================================================================

def check_voice_profile_freshness(client_id: str, max_age_days: int = 30) -> Dict[str, Any]:
    """
    Check the freshness of voice profiles for a client.

    Args:
        client_id: Client UUID
        max_age_days: Maximum age in days before profile is considered stale

    Returns:
        Dictionary with freshness status for each profile
    """
    supabase = get_supabase_client()

    try:
        # Get all voice profiles for this client
        profiles_response = supabase.table("voice_profiles")\
            .select("subreddit, voice_profile, updated_at, comments_analyzed")\
            .eq("client_id", client_id)\
            .execute()

        if not profiles_response.data:
            return {
                "client_id": client_id,
                "total_profiles": 0,
                "fresh": 0,
                "stale": 0,
                "profiles": [],
                "message": "No voice profiles found for this client"
            }

        now = datetime.utcnow()
        cutoff = now - timedelta(days=max_age_days)

        fresh_profiles = []
        stale_profiles = []

        for profile in profiles_response.data:
            subreddit = profile.get('subreddit')
            voice_data = profile.get('voice_profile') or {}

            # Get last crawl date from voice_profile JSON or updated_at
            last_crawl_str = voice_data.get('last_crawl_date') or profile.get('updated_at')

            if last_crawl_str:
                try:
                    # Parse ISO format datetime
                    if 'T' in last_crawl_str:
                        last_crawl = datetime.fromisoformat(last_crawl_str.replace('Z', '+00:00').replace('+00:00', ''))
                    else:
                        last_crawl = datetime.strptime(last_crawl_str, '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    last_crawl = None
            else:
                last_crawl = None

            profile_info = {
                "subreddit": subreddit,
                "last_crawl": last_crawl.isoformat() if last_crawl else "unknown",
                "comments_analyzed": profile.get('comments_analyzed') or voice_data.get('comments_analyzed', 0),
                "learning_method": voice_data.get('learning_method', 'unknown'),
                "vocabulary_richness": voice_data.get('vocabulary_richness', 0)
            }

            if last_crawl and last_crawl >= cutoff:
                age_days = (now - last_crawl).days
                profile_info["status"] = "fresh"
                profile_info["age_days"] = age_days
                profile_info["days_until_stale"] = max_age_days - age_days
                fresh_profiles.append(profile_info)
            else:
                age_days = (now - last_crawl).days if last_crawl else "unknown"
                profile_info["status"] = "stale"
                profile_info["age_days"] = age_days
                profile_info["needs_refresh"] = True
                stale_profiles.append(profile_info)

        return {
            "client_id": client_id,
            "total_profiles": len(profiles_response.data),
            "fresh": len(fresh_profiles),
            "stale": len(stale_profiles),
            "max_age_days": max_age_days,
            "fresh_profiles": fresh_profiles,
            "stale_profiles": stale_profiles,
            "needs_refresh": len(stale_profiles) > 0
        }

    except Exception as e:
        logger.error(f"Error checking voice profile freshness for {client_id}: {e}")
        return {
            "client_id": client_id,
            "error": str(e),
            "total_profiles": 0,
            "fresh": 0,
            "stale": 0
        }


async def refresh_stale_voice_profiles(
    client_id: Optional[str] = None,
    max_age_days: int = 30,
    user_limit: int = 100,
    comments_per_user: int = 20
) -> Dict[str, Any]:
    """
    Refresh voice profiles that are older than max_age_days.

    This should be run on a schedule (e.g., daily) to keep profiles fresh.

    Args:
        client_id: Optional - refresh for specific client, or all clients if None
        max_age_days: Profiles older than this will be refreshed
        user_limit: Users to analyze per subreddit
        comments_per_user: Comments per user

    Returns:
        Summary of refresh operation
    """
    supabase = get_supabase_client()
    worker = VoiceDatabaseWorker()
    worker.TOP_USERS_PER_SUBREDDIT = user_limit
    worker.COMMENTS_PER_USER = comments_per_user

    try:
        # Get clients to process
        if client_id:
            clients = [client_id]
        else:
            # Get all active clients
            clients_response = supabase.table("clients")\
                .select("client_id")\
                .execute()
            clients = [c['client_id'] for c in (clients_response.data or [])]

        if not clients:
            return {
                "success": True,
                "message": "No clients found",
                "refreshed": 0,
                "failed": 0
            }

        total_refreshed = 0
        total_failed = 0
        details = []

        for cid in clients:
            # Check freshness for this client
            freshness = check_voice_profile_freshness(cid, max_age_days)

            if not freshness.get('stale_profiles'):
                logger.info(f"Client {cid}: All {freshness.get('fresh', 0)} profiles are fresh")
                continue

            stale = freshness['stale_profiles']
            logger.info(f"Client {cid}: Refreshing {len(stale)} stale voice profiles")

            for profile_info in stale:
                subreddit = profile_info['subreddit']
                try:
                    logger.info(f"🔄 Refreshing r/{subreddit} for client {cid}...")
                    await worker.analyze_subreddit_voice(
                        subreddit,
                        cid,
                        user_limit=user_limit,
                        comments_per_user=comments_per_user
                    )
                    total_refreshed += 1
                    details.append({
                        "client_id": cid,
                        "subreddit": subreddit,
                        "status": "refreshed",
                        "previous_age_days": profile_info.get('age_days')
                    })
                    logger.info(f"✅ Refreshed r/{subreddit}")
                except Exception as e:
                    total_failed += 1
                    details.append({
                        "client_id": cid,
                        "subreddit": subreddit,
                        "status": "failed",
                        "error": str(e)
                    })
                    logger.error(f"❌ Failed to refresh r/{subreddit}: {e}")

        return {
            "success": True,
            "clients_processed": len(clients),
            "refreshed": total_refreshed,
            "failed": total_failed,
            "details": details
        }

    except Exception as e:
        logger.error(f"Error in refresh_stale_voice_profiles: {e}")
        return {
            "success": False,
            "error": str(e),
            "refreshed": 0,
            "failed": 0
        }


async def scheduled_voice_profile_refresh():
    """
    Scheduled task to refresh stale voice profiles.
    Call this from your scheduler (e.g., daily via APScheduler or cron).
    """
    logger.info("=" * 70)
    logger.info("🔄 SCHEDULED VOICE PROFILE REFRESH STARTING")
    logger.info("=" * 70)

    result = await refresh_stale_voice_profiles(
        max_age_days=30,
        user_limit=100,
        comments_per_user=20
    )

    logger.info(f"📊 Refresh complete: {result.get('refreshed', 0)} refreshed, {result.get('failed', 0)} failed")
    logger.info("=" * 70)

    return result
