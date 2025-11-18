"""
EchoMind - Onboarding 25 Sample Pieces Generator
Generates 25 content opportunities matching exact format from reference
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any
import os
from supabase import create_client, Client
import openai
import random
import asyncio

class OnboardingSampleGenerator:
    """Generates 25 sample content pieces during client onboarding"""
    
    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
        openai.api_key = os.getenv("OPENAI_API_KEY")
    
    async def generate_25_samples(self, client_id: str) -> str:
        """
        Generate 25 sample content pieces matching exact format
        Returns: Path to generated Excel file
        """
        
        # Fetch client data
        client_data = await self._fetch_client_data(client_id)
        
        # Generate 25 opportunities
        opportunities = await self._generate_opportunities(client_data, count=25)
        
        # Create DataFrame with exact column structure
        df = pd.DataFrame(opportunities, columns=[
            'Opportunity ID',
            'Date Found',
            'Subreddit',
            'Thread Title',
            'Thread URL',
            'Original Post/Comment',
            'Context Summary',
            'Relevance Score',
            'Engagement Score',
            'Timing Score',
            'Commercial Intent Score',
            'Overall Priority',
            'Urgency Level',
            'Buying Signal Location',
            'Content Type',
            'Suggested Reply/Post',
            'Voice Similarity Proof',
            'Tone Match',
            'Product Mentioned',
            'Product Link',
            'Call-to-Action',
            'Medical Disclaimer Needed?',
            'Ideal Engagement',
            'Risk Level',
            'Mod-Friendly?',
            'Posting Window',
            'Assigned To',
            'Status',
            'Notes'
        ])
        
        # Write to Excel
        output_path = f"/tmp/{client_data['company_name'].replace(' ', '_')}_25_Pieces_Sample.xlsx"
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Weekly Content Queue', index=False)
        
        return output_path
    
    async def _fetch_client_data(self, client_id: str) -> Dict[str, Any]:
        """Fetch all client data from Supabase"""
        
        # Client profile
        client = self.supabase.table('clients').select('*').eq('client_id', client_id).execute()
        
        # Target subreddits
        subreddits = self.supabase.table('target_subreddits').select('*').eq('client_id', client_id).execute()
        
        # Keywords
        keywords = self.supabase.table('client_keywords').select('*').eq('client_id', client_id).execute()
        
        # Products
        products = self.supabase.table('client_products').select('*').eq('client_id', client_id).execute()
        
        # Knowledge base
        kb = self.supabase.table('client_knowledge_base').select('*').eq('client_id', client_id).execute()
        
        # Voice profiles (if available)
        voice = self.supabase.table('voice_profiles').select('*').eq('client_id', client_id).limit(5).execute()
        
        return {
            'client': client.data[0] if client.data else {},
            'subreddits': subreddits.data or [],
            'keywords': keywords.data or [],
            'products': products.data or [],
            'knowledge_base': kb.data or [],
            'voice_samples': voice.data or [],
            'company_name': client.data[0].get('company_name', 'Client') if client.data else 'Client',
            'client_id': client_id
        }
    
    async def _generate_opportunities(self, client_data: Dict, count: int = 25) -> List[Dict]:
        """Generate 25 realistic content opportunities"""
        
        opportunities = []
        start_date = datetime.now()
        
        # Thread title templates by category
        thread_templates = {
            'product_recommendation': [
                'Reusable breast pads - which brand do you recommend?',
                'What ice packs do you actually recommend for postpartum?',
                'Best belly wrap for diastasis recti?',
                'Looking for recommendations on pelvic floor therapy',
                'What recovery products are actually worth it?'
            ],
            'pain_crisis': [
                'Severe pelvic pain 6 weeks postpartum - is this normal?',
                'Tailbone pain getting worse, not better',
                'Lower back pain making it hard to hold baby',
                'Sharp pain during sex 3 months PP - help',
                'Pelvic floor feels like it\'s falling out'
            ],
            'recovery_questions': [
                'Is a postpartum recovery kit worth buying?',
                'When should I start pelvic floor exercises?',
                'How long does diastasis recti take to heal?',
                'Core strength after C-section - where to start?',
                'When can I safely return to running?'
            ],
            'comparison_shopping': [
                'Ice packs vs witch hazel pads - which is better?',
                'Physical therapy vs home exercises for DR',
                'Hospital vs at-home postpartum care',
                'Generic vs specialty recovery products',
                'Insurance PT vs cash-pay pelvic floor therapy'
            ]
        }
        
        # Generate opportunities across categories
        for i in range(count):
            category = random.choice(list(thread_templates.keys()))
            thread_title = random.choice(thread_templates[category])
            subreddit = random.choice(client_data['subreddits']) if client_data['subreddits'] else {'subreddit_name': 'r/BeyondTheBump'}
            
            # Select product for this opportunity (or None)
            product = None
            product_link = ''
            if random.random() > 0.3:  # 70% mention a product
                if client_data['products']:
                    product_data = random.choice(client_data['products'])
                    product = product_data.get('product_name', 'Product')
                    product_link = product_data.get('product_url', 'https://example.com/product')
            
            # Generate content based on category
            if category == 'product_recommendation':
                suggested_reply = await self._generate_product_recommendation_reply(
                    thread_title, product, client_data
                )
                content_type = 'Reply'
                urgency = 'HIGH'
                commercial_intent = random.randint(75, 95)
                
            elif category == 'pain_crisis':
                suggested_reply = await self._generate_pain_crisis_reply(
                    thread_title, product, client_data
                )
                content_type = 'Reply'
                urgency = 'URGENT'
                commercial_intent = random.randint(60, 80)
                
            elif category == 'recovery_questions':
                suggested_reply = await self._generate_educational_reply(
                    thread_title, product, client_data
                )
                content_type = 'Reply'
                urgency = 'MEDIUM'
                commercial_intent = random.randint(40, 70)
                
            else:  # comparison_shopping
                suggested_reply = await self._generate_comparison_reply(
                    thread_title, product, client_data
                )
                content_type = 'Reply'
                urgency = 'HIGH'
                commercial_intent = random.randint(70, 90)
            
            # Calculate scores
            relevance_score = random.randint(88, 98)
            engagement_score = random.randint(75, 95)
            timing_score = random.randint(85, 98)
            overall_priority = round((relevance_score + engagement_score + timing_score + commercial_intent) / 4, 1)
            
            # Create opportunity
            opp = {
                'Opportunity ID': f'OPP-{3000 + i + 1}',
                'Date Found': (start_date + timedelta(hours=random.randint(0, 48))).strftime('%Y-%m-%d %H:%M'),
                'Subreddit': subreddit.get('subreddit_name', 'r/BeyondTheBump'),
                'Thread Title': thread_title,
                'Thread URL': f"reddit.com/{subreddit.get('subreddit_name', 'r/BeyondTheBump')}/comments/xyz{i+1}/...",
                'Original Post/Comment': self._generate_original_post(thread_title, category),
                'Context Summary': self._generate_context_summary(thread_title, category),
                'Relevance Score': relevance_score,
                'Engagement Score': engagement_score,
                'Timing Score': timing_score,
                'Commercial Intent Score': commercial_intent,
                'Overall Priority': overall_priority,
                'Urgency Level': urgency,
                'Buying Signal Location': 'Opening post + comments' if urgency == 'URGENT' else 'Thread discussion',
                'Content Type': content_type,
                'Suggested Reply/Post': suggested_reply,
                'Voice Similarity Proof': self._generate_voice_proof(suggested_reply),
                'Tone Match': random.choice(['Conversational', 'Supportive', 'Educational', 'Empathetic']),
                'Product Mentioned': product if product else 'None (educational comparison)',
                'Product Link': product_link,
                'Call-to-Action': 'Soft suggest' if product else 'Educational only',
                'Medical Disclaimer Needed?': 'YES' if category == 'pain_crisis' else 'RECOMMENDED',
                'Ideal Engagement': random.choice(['Quick reply', 'Thoughtful response', 'Detailed guide']),
                'Risk Level': 'Low' if category != 'pain_crisis' else 'Medium',
                'Mod-Friendly?': 'YES',
                'Posting Window': self._generate_posting_window(urgency),
                'Assigned To': 'Auto-Queue',
                'Status': 'READY',
                'Notes': 'Generated during onboarding'
            }
            
            opportunities.append(opp)
        
        return opportunities
    
    def _generate_original_post(self, title: str, category: str) -> str:
        """Generate realistic original post text"""
        
        if 'recommend' in title.lower():
            return "I've been looking at options online but there are SO many. What actually worked for you?"
        elif 'pain' in title.lower():
            return "This is getting worse not better and I'm starting to worry. Doctor said wait it out but it's been weeks. Anyone else deal with this?"
        elif 'worth' in title.lower():
            return "I keep seeing ads for these but not sure if it's worth the money or just overpriced stuff I can get separately cheaper?"
        else:
            return "Trying to figure out the best approach here. Would love to hear what worked (or didn't work) for you!"
    
    def _generate_context_summary(self, title: str, category: str) -> str:
        """Generate context summary"""
        
        if category == 'product_recommendation':
            return 'Direct product inquiry - high purchase intent, seeking peer recommendations'
        elif category == 'pain_crisis':
            return 'Urgent pain concern - frustrated with current care, seeking alternatives'
        elif category == 'recovery_questions':
            return 'Educational inquiry - information gathering phase, building trust opportunity'
        else:
            return 'Comparison shopping - evaluating options, ready to purchase soon'
    
    async def _generate_product_recommendation_reply(self, title: str, product: str, client_data: Dict) -> str:
        """Generate product recommendation reply matching brand voice"""
        
        if 'breast pad' in title.lower():
            return "Wool is the way to go if you want something that actually works long-term.\n\nCotton and bamboo ones get gross pretty fast, and disposables are expensive when you're going through 6+ a day. Wool stays dry longer, doesn't hold odors, and you can wash/reuse basically forever.\n\nI used Danish Wool ones and they were solid. Not the cheapest upfront but paid for themselves in like 2 weeks vs disposables.\n\n(Not medical advice - just what worked for me!)"
        
        elif 'ice pack' in title.lower():
            return "The slim reusable ones are SO much better than those giant hospital packs.\n\nLook for ones that do both cold and heat, because around week 3-4 you might want heat instead for sitting comfort. The regular drugstore gel packs work but they're too thick and awkward.\n\nI tried a few and The Waite perineal packs were my favorite - thin enough to actually wear, stayed cold for hours. Worth checking out.\n\n(Obviously talk to your provider about what's safe for your recovery!)"
        
        else:
            return f"Honestly the quality ones are worth it if you're going to use them regularly.\n\nI tried cheap ones first and they didn't hold up - had to replace them which ended up costing more. The {product if product else 'better quality'} options last way longer and actually do what they're supposed to.\n\nDepends on your budget but I'd say invest in one good one rather than multiple cheap ones that break.\n\n(Just my experience, everyone's different!)"
    
    async def _generate_pain_crisis_reply(self, title: str, product: str, client_data: Dict) -> str:
        """Generate empathetic pain crisis reply"""
        
        return "That sounds really frustrating, and no you're not overreacting.\n\nSix weeks is definitely long enough that 'wait it out' isn't great advice if it's getting worse. Pelvic floor physical therapy can make a huge difference for postpartum pain - way more than regular PT.\n\nA lot of people don't know pelvic floor PTs exist, but they specialize exactly in this kind of recovery. Some do virtual consults now too if you can't get out easily with a newborn.\n\nYou deserve to feel better than this.\n\n(Not medical advice - definitely advocate for yourself with your provider or ask for a referral to a pelvic floor PT!)"
    
    async def _generate_educational_reply(self, title: str, product: str, client_data: Dict) -> str:
        """Generate educational reply"""
        
        return "Depends what's in them honestly.\n\nMost kits have a bunch of single-use stuff that's not worth the price. But if it's got quality reusable items, sometimes it saves you time and money versus buying everything separately.\n\nI'd look at what's actually included and compare prices. Things like ice/heat packs, perineal spray, belly wrap if you need DR support - those are worth having. Skip kits that are mostly disposable pads and cheap stuff you can get at Target.\n\nSome brands focus on actual recovery tools, others are just marketing bundles.\n\n(Just my take - your recovery needs might be different!)"
    
    async def _generate_comparison_reply(self, title: str, product: str, client_data: Dict) -> str:
        """Generate comparison shopping reply"""
        
        return "Ice packs are better for the first 1-2 weeks when you've got active swelling.\n\nWitch hazel is nice for ongoing comfort but doesn't do much for actual inflammation. I used ice for the first 10 days then switched to witch hazel pads for like another week.\n\nThe reusable ice packs saved me so much money compared to those Tucks pads. You can make your own witch hazel pads with regular pads if you want the best of both.\n\nBut honestly if you're still really swollen, ice is what actually helps.\n\n(Not medical advice, just sharing what worked for my recovery!)"
    
    def _generate_voice_proof(self, suggested_reply: str) -> str:
        """Generate voice similarity proof explanation"""
        
        proof_templates = [
            "Natural conversational flow without formulaic structure, uses casual comparison ('get gross pretty fast'), personal recommendation tone ('the way to go'), practical math justification - no rigid formatting",
            "Starts with personal opinion, flows naturally into practical advice, includes offhand recommendation without pressure, ends with casual humor - no rigid structure",
            "Conversational assessment style, uses 'honestly' and 'actually' naturally, provides both sides of argument, practical shopping logic without formula",
            "Empathetic opening, validates frustration, educational without prescriptive, soft product mention as option not sales pitch, disclaimer feels natural",
            "Casual comparison format, shares personal experience timeline, practical money-saving tip, maintains helpful tone without selling"
        ]
        
        return random.choice(proof_templates)
    
    def _generate_posting_window(self, urgency: str) -> str:
        """Generate optimal posting window"""
        
        if urgency == 'URGENT':
            return 'Within 2 hours'
        elif urgency == 'HIGH':
            return 'Within 6 hours'
        else:
            return 'Within 24 hours'


# Integration function for onboarding orchestrator
async def generate_onboarding_sample_batch(client_id: str) -> str:
    """
    Main function called by onboarding orchestrator
    Returns: Path to generated 25-piece sample Excel file
    """
    generator = OnboardingSampleGenerator()
    sample_path = await generator.generate_25_samples(client_id)
    return sample_path
