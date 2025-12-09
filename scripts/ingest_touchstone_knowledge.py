#!/usr/bin/env python3
"""
Script to directly ingest Touchstone product knowledge into the RAG system.
Run this locally to populate the knowledge base.

Usage:
    python scripts/ingest_touchstone_knowledge.py

Environment variables required (from Railway or local .env):
    - SUPABASE_URL
    - SUPABASE_KEY
    - OPENAI_API_KEY
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import OpenAI
from supabase import create_client, Client

# Touchstone client ID (from previous session)
TOUCHSTONE_CLIENT_ID = "83a4fe57-4737-4dcf-b4bc-c9300686112f"

# Product knowledge to ingest
KNOWLEDGE_CHUNKS = [
    {
        "title": "Touchstone Electric Fireplace Overview",
        "category": "brand",
        "content": "Touchstone Home Products specializes in premium electric fireplaces designed for modern living. Founded to bring the ambiance of a real fire without the hassle of wood or gas, Touchstone offers wall-mounted, recessed, and freestanding electric fireplaces. All units are zone-rated supplemental heaters producing up to 5,000 BTU of heat, capable of warming rooms up to 400 square feet. Touchstone fireplaces feature realistic LED flame technology with multiple color options and intensity settings."
    },
    {
        "title": "Sideline Elite Series - 50 inch (Model 80036)",
        "category": "product",
        "content": "The Sideline Elite 50 is a premium recessed electric fireplace. Dimensions: 50 inches wide x 21.5 inches tall x 5.5 inches deep. Heat output: 5,000 BTU with dual heat settings (1500W high, 750W low). Features include: realistic multicolor flame with 60+ color combinations, ember bed lighting, adjustable flame speed and brightness, timer function (0.5 to 7.5 hours), thermostat control, and remote control included. Designed for recessing into a 2x4 or 2x6 wall. UL and CSA certified. Ideal for living rooms, bedrooms, and finished basements. Can be used with or without heat for year-round ambiance."
    },
    {
        "title": "Sideline Elite Series - 60 inch (Model 80037)",
        "category": "product",
        "content": "The Sideline Elite 60 is the mid-size option in the Elite series. Dimensions: 60 inches wide x 21.5 inches tall x 5.5 inches deep. Heat output: 5,000 BTU with dual heat settings. Same premium features as the 50-inch model including 60+ flame color combinations, ember bed lighting, timer, thermostat, and remote. Recesses into 2x4 or 2x6 walls. Perfect for medium to large living spaces. Front glass remains cool to touch during operation. Can be installed above or below a TV with proper spacing (minimum 12 inches from TV)."
    },
    {
        "title": "Sideline Elite Series - 72 inch (Model 80038)",
        "category": "product",
        "content": "The Sideline Elite 72 is the largest in the Elite series for dramatic impact. Dimensions: 72 inches wide x 21.5 inches tall x 5.5 inches deep. Heat output: 5,000 BTU with dual heat settings. Features 60+ multicolor flame combinations, LED technology, ember bed lighting, programmable timer, built-in thermostat, and included remote. Designed for large great rooms, master suites, or commercial spaces. Recesses into standard 2x4 or 2x6 walls. Installation can be DIY or professional."
    },
    {
        "title": "Sideline Elite Series - 84 inch (Model 80039)",
        "category": "product",
        "content": "The Sideline Elite 84 is the flagship model for maximum visual impact. Dimensions: 84 inches wide x 21.5 inches tall x 5.5 inches deep. Heat output: 5,000 BTU (same as smaller models - heater capacity is standard across the line). Premium features include 60+ flame color options, realistic ember bed, adjustable flame intensity and speed, 0.5-7.5 hour timer, thermostat, and remote control. Best suited for expansive walls, luxury homes, and commercial installations. Requires 2x4 or 2x6 wall recess."
    },
    {
        "title": "Heat Specifications and Safety",
        "category": "spec",
        "content": "All Touchstone electric fireplaces produce 5,000 BTU of supplemental heat, sufficient to warm rooms up to 400 square feet. Two heat settings available: High (1500W) and Low (750W). Operating voltage: 120V standard household outlet. Flame-only mode available for year-round ambiance without heat. Safety features include: auto-shutoff timer, overheat protection, cool-to-touch glass front. UL and CSA certified. Not intended as primary heat source. Safe for homes with children and pets."
    },
    {
        "title": "Installation Requirements",
        "category": "spec",
        "content": "Touchstone recessed fireplaces are designed for installation into 2x4 or 2x6 wall cavities. Minimum clearances: 12 inches from ceiling, 12 inches from any TV or electronics above, floor-level or raised installation options. Hardwired or plug-in installation available on most models. No venting required - 100% efficient electric heat. Can be installed on interior or exterior walls. Professional installation recommended but DIY-friendly with included mounting hardware and instructions. Fireplaces can be recessed fully flush or semi-recessed."
    },
    {
        "title": "Flame Technology and Ambiance",
        "category": "spec",
        "content": "Touchstone fireplaces use proprietary LED flame technology with lifelike flame effects. Over 60 flame color combinations available on Elite models including orange, blue, purple, green, and multicolor options. Adjustable flame intensity (brightness) from subtle glow to vivid flames. Variable flame speed control from slow romantic flicker to lively dancing flames. Ember bed lighting with color-changing options. Crystal or log media included depending on model. Flames operate independently of heat function."
    },
    {
        "title": "Comparison vs Gas Fireplaces",
        "category": "faq",
        "content": "Electric fireplaces vs gas fireplaces: Electric requires no venting, gas lines, or annual inspections. Electric is 100% efficient (all energy becomes heat), gas loses heat through venting. Electric installation costs $200-500 typical, gas installation costs $3,000-6,000+. Electric operating costs around $0.15/hour on high, gas costs $0.50-1.00/hour depending on fuel prices. Electric is safer with no combustion, carbon monoxide, or real flame. Electric offers more flame color options and smart controls. Gas provides more realistic flame appearance and higher BTU output (20,000+ BTU)."
    },
    {
        "title": "Comparison vs Wood-Burning Fireplaces",
        "category": "faq",
        "content": "Electric vs wood-burning: Electric requires no chimney, flue cleaning, or wood storage. Electric has no smoke, ash, sparks, or fire risk from embers. Electric operates with a remote control - no fire building required. Electric can be installed in any room, apartments, or condos where wood burning is prohibited. Electric has consistent heat output, wood varies with fuel quality. Electric costs less to operate long-term with no wood purchases. Wood-burning provides authentic crackling sounds and wood smoke aroma that electric cannot replicate."
    },
    {
        "title": "TV Mounting Above Fireplace",
        "category": "faq",
        "content": "Mounting a TV above a Touchstone electric fireplace is safe and common. Maintain minimum 12-inch clearance between the top of the fireplace and bottom of the TV. Electric fireplaces produce minimal upward heat - the glass front stays cool to touch. Use a full-motion TV mount to angle the screen down for optimal viewing. Consider a mantel shelf between fireplace and TV for visual separation. Many customers successfully mount 55-inch to 75-inch TVs above Sideline Elite models. No heat damage risk to electronics when following clearance guidelines."
    },
    {
        "title": "Touchstone Value Proposition",
        "category": "brand",
        "content": "Touchstone electric fireplaces offer premium features at competitive prices. 3-year warranty on all products. Free shipping on most orders. 60-day return policy. Made with durable steel construction and tempered safety glass. Energy-efficient LED technology - flames cost less than $0.01/hour to operate. Flame-only mode for year-round use. Smart home compatible models available. Trusted by over 100,000 homeowners. Featured in home improvement shows and publications. Based in USA with responsive customer support."
    }
]


def main():
    # Get credentials from environment
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    openai_api_key = os.getenv('OPENAI_API_KEY')

    if not all([supabase_url, supabase_key, openai_api_key]):
        print("Missing environment variables. Required:")
        print("  - SUPABASE_URL")
        print("  - SUPABASE_KEY")
        print("  - OPENAI_API_KEY")
        print("\nYou can set them inline:")
        print('  SUPABASE_URL="..." SUPABASE_KEY="..." OPENAI_API_KEY="..." python scripts/ingest_touchstone_knowledge.py')
        sys.exit(1)

    # Initialize clients
    print("Initializing clients...")
    supabase: Client = create_client(supabase_url, supabase_key)
    openai_client = OpenAI(api_key=openai_api_key)

    # Verify client exists
    print(f"Verifying client {TOUCHSTONE_CLIENT_ID}...")
    client = supabase.table("clients").select("company_name").eq("client_id", TOUCHSTONE_CLIENT_ID).execute()
    if not client.data:
        print(f"Client {TOUCHSTONE_CLIENT_ID} not found!")
        sys.exit(1)

    company_name = client.data[0].get('company_name', 'Touchstone')
    print(f"Found client: {company_name}")

    # Process each chunk
    print(f"\nIngesting {len(KNOWLEDGE_CHUNKS)} knowledge chunks...")
    embeddings_created = 0
    errors = []

    for idx, chunk in enumerate(KNOWLEDGE_CHUNKS):
        try:
            full_text = f"{chunk['title']}\n\n{chunk['content']}"

            # Generate embedding
            print(f"  [{idx+1}/{len(KNOWLEDGE_CHUNKS)}] Generating embedding for: {chunk['title'][:50]}...")
            response = openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=full_text[:8000]
            )
            embedding = response.data[0].embedding

            # Store in document_embeddings
            embedding_record = {
                'document_id': None,  # No document - direct ingestion
                'client_id': TOUCHSTONE_CLIENT_ID,
                'chunk_text': full_text,
                'chunk_index': idx,
                'embedding': embedding,
                'metadata': {
                    'title': chunk['title'],
                    'category': chunk['category'],
                    'source': 'manual_product_ingestion',
                    'char_count': len(full_text),
                    'company_name': company_name,
                    'ingested_at': datetime.utcnow().isoformat()
                },
                'created_at': datetime.utcnow().isoformat()
            }

            supabase.table('document_embeddings').insert(embedding_record).execute()
            embeddings_created += 1
            print(f"       Created embedding (chars: {len(full_text)})")

        except Exception as e:
            print(f"       ERROR: {e}")
            errors.append({"title": chunk['title'], "error": str(e)})

    # Summary
    print("\n" + "="*60)
    print("INGESTION COMPLETE")
    print("="*60)
    print(f"Client: {company_name}")
    print(f"Chunks submitted: {len(KNOWLEDGE_CHUNKS)}")
    print(f"Embeddings created: {embeddings_created}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err['title']}: {err['error']}")

    # Verify RAG data
    print("\nVerifying RAG data...")
    rag_check = supabase.table("document_embeddings")\
        .select("id, metadata")\
        .eq("client_id", TOUCHSTONE_CLIENT_ID)\
        .execute()
    print(f"Total embeddings for Touchstone: {len(rag_check.data)}")


if __name__ == "__main__":
    main()
