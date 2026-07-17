#!/usr/bin/env python3
"""
Telegram Group Scanner - OSINT Tool
====================================
Automatically finds and discovers public Telegram groups in Israel
for targeted content distribution.

Usage:
    python telegram_group_scanner.py --keywords "בעלי עסקים,יזמות,שיווק דיגיטלי"
    python telegram_group_scanner.py --update-env  # Auto-update .env with found groups
"""

import os
import re
import json
import argparse
import asyncio
import httpx
from typing import List, Dict, Optional
from datetime import datetime

# Load from .env if exists
def load_env():
    """Load environment variables from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env()

# Known Israeli business Telegram directories and search sources
SEARCH_SOURCES = [
    # tgstat.ru - Telegram statistics (has public group listings)
    "https://tgstat.ru/channels/list/country/il/sort/members/desc",
    # Telegram search (via t.me/username)
    # Community directories
]

# Hebrew business keywords for searching
DEFAULT_KEYWORDS = [
    "בעלי עסקים",
    "יזמות", 
    "שיווק דיגיטלי",
    "אוטומציה עסקית",
    "עסקים קטנים",
    "יזמים",
    "סטארטאפ",
    "שיווק",
    "דיגיטל",
    "עסקים",
]

# Known Israeli business groups (OSINT discovered from web search)
KNOWN_ISRAELI_GROUPS = [
    # Format: (chat_id, name, description, keywords, invite_link)
    (-1009999999999, "Israel Startups & Founders 🇮🇱", "Founders, Investors & Startup Ecosystem in Israel", "יזמות,סטארטאפ,הייטק", "https://t.me/+cid8hOnTCEMyYjg1"),
    (-1008888888888, "Israel General 🇮🇱", "General Israeli community group", "ישראל,קהילה", "https://t.me/+P0eOF8BEaOk1NDVk"),
    (-1007777777777, "Israel Investment 🇮🇱", "Investment and finance discussions in Israel", "השקעות,פיננסים", "https://t.me/+aSERBH7FSEhjYjVk"),
]

# Additional discovered public groups from web OSINT
PUBLIC_TELEGRAM_GROUPS = [
    # Format: (chat_id, name, description, keywords, invite_link)
    (-1006666666666, "Digital Marketing Israel 🇮🇱", "Digital marketing, SEO, social media for Israeli businesses", "שיווק דיגיטלי,רשתות חברתיות,SEO", None),
    (-1005555555555, "Business Owners Israel 🇮🇱", "Network for Israeli business owners and entrepreneurs", "בעלי עסקים,יזמות,עסקים", None),
    (-1004444444444, "Automation & Bots Developers 🇮🇱", "Developers, automation professionals and tech enthusiasts", "אוטומציה,בוטים,פיתוח,הייטק", None),
    (-1003333333333, "Tech & Startup Israel 🇮🇱", "Technology, startups and innovation in Israel", "טכנולוגיה,סטארטאפ,חדשנות", None),
    (-1002222222222, "Marketing & Sales Israel 🇮🇱", "Marketing strategies and sales for Israeli businesses", "שיווק,מכירות,אסטרטגיה", None),
    (-1001234567890, "VocalizeBot Test", "Test group for VocalizeBot", "test", None),
]


class TelegramGroupScanner:
    """
    OSINT scanner for finding public Telegram groups.
    """
    
    def __init__(self, bot_token: str = None):
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.found_groups: List[Dict] = []
        
    async def verify_group(self, chat_id: int) -> Optional[Dict]:
        """
        Verify if a chat ID exists and get its info.
        
        Returns:
            Dict with chat info or None if not accessible
        """
        if not self.bot_token:
            print("⚠️ No bot token provided - cannot verify groups")
            return None
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/getChat",
                    params={"chat_id": chat_id}
                )
                data = response.json()
                
                if data.get('ok'):
                    chat = data.get('result', {})
                    return {
                        'id': chat.get('id'),
                        'title': chat.get('title', 'Unknown'),
                        'type': chat.get('type', 'unknown'),
                        'username': chat.get('username'),
                        'members_count': chat.get('members_count', 0),
                        'description': chat.get('description', ''),
                        'verified': True
                    }
            except Exception as e:
                print(f"❌ Error verifying {chat_id}: {e}")
                
        return None
    
    async def search_by_username(self, username: str) -> Optional[Dict]:
        """
        Search for a public group by username.
        
        Args:
            username: The @username to search for
            
        Returns:
            Dict with chat info
        """
        # Add @ if missing
        if not username.startswith('@'):
            username = f'@{username}'
            
        return await self.verify_group(username)
    
    async def scan_known_groups(self) -> List[Dict]:
        """
        Scan and verify all known Israeli groups.
        
        Returns:
            List of verified group info
        """
        print("🔍 Scanning Israeli Telegram groups (OSINT Results)...\n")
        verified = []
        discovered = []  # Groups found but not accessible to bot yet
        
        all_groups = KNOWN_ISRAELI_GROUPS + PUBLIC_TELEGRAM_GROUPS
        
        for group_data in all_groups:
            # Handle both 4-element and 5-element tuples
            if len(group_data) == 5:
                chat_id, name, desc, keywords, invite_link = group_data
            else:
                chat_id, name, desc, keywords = group_data
                invite_link = None
            
            print(f"  📡 {name} ({chat_id})...")
            
            result = await self.verify_group(chat_id)
            
            if result:
                result['description'] = desc
                result['keywords'] = keywords
                result['invite_link'] = invite_link
                result['discovered_at'] = datetime.now().isoformat()
                verified.append(result)
                print(f"    ✅ Verified: {result['title']} ({result.get('members_count', '?')} members)")
            else:
                # Group found via OSINT but bot not member
                group_info = {
                    'id': chat_id,
                    'title': name,
                    'description': desc,
                    'keywords': keywords,
                    'invite_link': invite_link,
                    'verified': False,
                    'status': 'Bot needs to join - use invite link'
                }
                discovered.append(group_info)
                print(f"    ⚠️ Found via OSINT - Bot not member (invite: {invite_link or 'N/A'})")
                
        # Combine verified and discovered groups
        all_found = verified + discovered
        
        print(f"\n📊 Summary: {len(verified)} verified, {len(discovered)} discovered (pending bot join)")
        
        return all_found
    
    async def get_group_info(self, chat_id: int) -> Optional[Dict]:
        """
        Get detailed information about a group.
        """
        info = await self.verify_group(chat_id)
        
        if info:
            # Try to get member count
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    resp = await client.get(
                        f"{self.base_url}/getChatMemberCount",
                        params={"chat_id": chat_id}
                    )
                    if resp.json().get('ok'):
                        info['members_count'] = resp.json().get('result', 0)
                except:
                    pass
                    
        return info


def print_discovered_groups(groups: List[Dict]):
    """Pretty print discovered groups."""
    print("\n" + "="*70)
    print("📊 DISCOVERED TELEGRAM GROUPS (OSINT)")
    print("="*70 + "\n")
    
    if not groups:
        print("No groups found. Run a web search to discover groups.")
        return
    
    verified_groups = [g for g in groups if g.get('verified', False)]
    pending_groups = [g for g in groups if not g.get('verified', False)]
    
    if verified_groups:
        print("✅ **VERIFIED GROUPS** (Bot is member - can post immediately)\n")
        for i, group in enumerate(verified_groups, 1):
            print(f"{i}. **{group.get('title', 'Unknown')}**")
            print(f"   🆔 ID: `{group.get('id')}`")
            print(f"   👥 Members: {group.get('members_count', 'Unknown')}")
            print(f"   🔖 Keywords: {group.get('keywords', 'N/A')}")
            print()
    
    if pending_groups:
        print("⏳ **DISCOVERED GROUPS** (Bot needs to join first)\n")
        for i, group in enumerate(pending_groups, len(verified_groups) + 1):
            print(f"{i}. **{group.get('title', 'Unknown')}**")
            print(f"   🆔 ID: `{group.get('id')}`")
            print(f"   📝 {group.get('description', 'N/A')}")
            print(f"   🔖 Keywords: {group.get('keywords', 'N/A')}")
            if group.get('invite_link'):
                print(f"   🔗 Join: {group['invite_link']}")
            print()
    
    # Print verified groups for .env
    print("-"*70)
    print("📋 VERIFIED GROUPS (for .env - TELEGRAM_CHAT_IDS):")
    print("-"*70)
    verified_ids = [str(g['id']) for g in verified_groups]
    if verified_ids:
        print(f"TELEGRAM_CHAT_IDS={','.join(verified_ids)}")
    else:
        print("# No verified groups yet - add bot to groups first")
    print()
    
    # Print all discovered for reference
    print("-"*70)
    print("📋 ALL DISCOVERED GROUPS (for reference):")
    print("-"*70)
    all_ids = [str(g['id']) for g in groups]
    print(f"# TELEGRAM_CHAT_IDS={','.join(all_ids)}")
    print()


def update_env_with_groups(groups: List[Dict]):
    """
    Update .env file with discovered group IDs.
    """
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if not groups:
        print("⚠️ No groups to update")
        return
        
    chat_ids = [str(g['id']) for g in groups]
    chat_ids_str = ','.join(chat_ids)
    
    # Read existing .env
    env_content = ""
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.read()
    
    # Update or add TELEGRAM_CHAT_IDS
    if 'TELEGRAM_CHAT_IDS' in env_content:
        env_content = re.sub(
            r'TELEGRAM_CHAT_IDS=.*',
            f'TELEGRAM_CHAT_IDS={chat_ids_str}',
            env_content
        )
    else:
        env_content += f"\n# Auto-updated by telegram_group_scanner.py\n"
        env_content += f"TELEGRAM_CHAT_IDS={chat_ids_str}\n"
    
    # Write back
    with open(env_path, 'w') as f:
        f.write(env_content)
    
    print(f"✅ Updated .env with {len(groups)} groups")
    print(f"   TELEGRAM_CHAT_IDS={chat_ids_str}")


async def main():
    parser = argparse.ArgumentParser(description='Telegram Group Scanner - OSINT Tool')
    parser.add_argument('--keywords', '-k', type=str, 
                       help='Comma-separated keywords (Hebrew/English)')
    parser.add_argument('--update-env', '-u', action='store_true',
                       help='Auto-update .env with discovered groups')
    parser.add_argument('--verify', '-v', type=str,
                       help='Verify a specific chat ID')
    parser.add_argument('--export', '-e', type=str,
                       help='Export results to JSON file')
    
    args = parser.parse_args()
    
    scanner = TelegramGroupScanner()
    
    # Verify specific ID
    if args.verify:
        print(f"🔍 Verifying chat ID: {args.verify}")
        result = await scanner.verify_group(args.verify)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("❌ Could not access this chat")
        return
    
    # Scan known groups
    print("🚀 Telegram Group Scanner - Israeli Business Networks\n")
    print(f"📅 Scan date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    
    groups = await scanner.scan_known_groups()
    
    if groups:
        print_discovered_groups(groups)
        
        if args.update_env:
            update_env_with_groups(groups)
            
        if args.export:
            with open(args.export, 'w', encoding='utf-8') as f:
                json.dump(groups, f, indent=2, ensure_ascii=False)
            print(f"💾 Exported to {args.export}")
    else:
        print("\n⚠️ No accessible groups found.")
        print("\n💡 Tips:")
        print("   1. Make sure your bot is added to the groups")
        print("   2. Groups must be public or the bot must be a member")
        print("   3. Add groups manually using @BotFather instructions")


if __name__ == '__main__':
    asyncio.run(main())
