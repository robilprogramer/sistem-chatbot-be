"""
Database Population & Verification Script
==========================================
Script untuk:
1. Verifikasi data di database
2. Populate tabel dari YAML jika kosong
3. Insert data ke tabel detail (steps, fields, messages, commands)
"""

import os
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()
# PostgreSQL connection
try:
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor
except ImportError:
    print("Installing psycopg2...")
    os.system("pip install psycopg2-binary")
    import psycopg2
    from psycopg2.extras import Json, RealDictCursor


class DatabasePopulator:
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL not set")
        
        self.conn = None
    
    def connect(self):
        """Connect to database"""
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(self.db_url)
        return self.conn
    
    def close(self):
        """Close connection"""
        if self.conn and not self.conn.closed:
            self.conn.close()
    
    def execute(self, query: str, params: tuple = None) -> List[Dict]:
        """Execute query and return results"""
        conn = self.connect()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            conn.commit()
            return []
    
    # =========================================================================
    # VERIFICATION
    # =========================================================================
    
    def verify_tables(self) -> Dict[str, int]:
        """Check row counts for all tables"""
        tables = [
            'form_configs',
            'form_steps', 
            'form_fields',
            'form_messages',
            'form_commands',
            'auto_triggers',
            'rating_prompts',
            'system_settings'
        ]
        
        counts = {}
        for table in tables:
            try:
                result = self.execute(f"SELECT COUNT(*) as count FROM {table}")
                counts[table] = result[0]['count'] if result else 0
            except Exception as e:
                counts[table] = f"ERROR: {e}"
        
        return counts
    
    def get_active_config(self) -> Dict:
        """Get active form config"""
        result = self.execute("""
            SELECT id, config_key, version, is_active, created_at
            FROM form_configs 
            WHERE is_active = true
            ORDER BY created_at DESC LIMIT 1
        """)
        return result[0] if result else None
    
    def show_config_data(self):
        """Show what's in the active config"""
        config = self.get_active_config()
        if not config:
            print("❌ No active config found!")
            return
        
        print(f"\n📋 Active Config ID: {config['id']}")
        print(f"   Key: {config['config_key']}")
        print(f"   Version: {config['version']}")
        
        # Get full config data
        result = self.execute("""
            SELECT config_data FROM form_configs WHERE id = %s
        """, (config['id'],))
        
        if result:
            data = result[0]['config_data']
            if isinstance(data, str):
                data = json.loads(data)
            
            print(f"\n   Form ID: {data.get('form', {}).get('id', 'N/A')}")
            print(f"   Steps: {len(data.get('steps', []))}")
            print(f"   Fields: {len(data.get('fields', {}))}")
            print(f"   Messages keys: {len(data.get('messages', {}))}")
            print(f"   Commands: {len(data.get('commands', {}))}")
    
    # =========================================================================
    # POPULATION FROM YAML
    # =========================================================================
    
    def load_yaml_config(self, yaml_path: str) -> Dict:
        """Load YAML configuration"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def populate_from_yaml(self, yaml_path: str, force: bool = False):
        """
        Populate all tables from YAML config.
        """
        print(f"\n📂 Loading YAML from: {yaml_path}")
        config = self.load_yaml_config(yaml_path)
        
        if force:
            print("⚠️  Force mode: Clearing existing data...")
            self._clear_form_data()
        
        # 1. Insert main config
        config_id = self._insert_form_config(config)
        print(f"✅ Inserted form_configs (ID: {config_id})")
        
        # 2. Insert steps
        steps_count = self._insert_steps(config_id, config.get('steps', []))
        print(f"✅ Inserted {steps_count} steps")
        
        # 3. Insert fields
        fields_count = self._insert_fields(config_id, config.get('fields', {}))
        print(f"✅ Inserted {fields_count} fields")
        
        # 4. Insert messages
        messages_count = self._insert_messages(config_id, config.get('messages', {}))
        print(f"✅ Inserted {messages_count} messages")
        
        # 5. Insert commands
        commands_count = self._insert_commands(config_id, config.get('commands', {}))
        print(f"✅ Inserted {commands_count} commands")
        
        # 6. Insert default triggers
        triggers_count = self._insert_default_triggers()
        print(f"✅ Inserted {triggers_count} auto_triggers")
        
        # 7. Insert rating prompts
        prompts_count = self._insert_rating_prompts()
        print(f"✅ Inserted {prompts_count} rating_prompts")
        
        # 8. Insert system settings
        settings_count = self._insert_system_settings()
        print(f"✅ Inserted {settings_count} system_settings")
        
        print(f"\n🎉 Database population completed!")
        return config_id
    
    def _clear_form_data(self):
        """Clear existing form data"""
        tables = ['form_commands', 'form_messages', 'form_fields', 'form_steps', 'form_configs']
        for table in tables:
            try:
                self.execute(f"DELETE FROM {table}")
            except:
                pass
    
    def _insert_form_config(self, config: Dict) -> int:
        """Insert main form config"""
        form_info = config.get('form', {})
        
        # Deactivate existing
        self.execute("UPDATE form_configs SET is_active = false WHERE is_active = true")
        
        # Insert new
        result = self.execute("""
            INSERT INTO form_configs (config_key, config_type, config_data, version, is_active)
            VALUES (%s, %s, %s, %s, true)
            RETURNING id
        """, (
            f"form_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            'yaml',
            Json(config),
            form_info.get('version', '1.0.0')
        ))
        
        return result[0]['id']
    
    def _insert_steps(self, config_id: int, steps: List[Dict]) -> int:
        """Insert form steps"""
        if not steps:
            return 0
        
        for step in steps:
            self.execute("""
                INSERT INTO form_steps 
                (config_id, step_id, step_name, description, step_order, 
                 is_mandatory, can_skip, skip_conditions, icon)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (config_id, step_id) DO UPDATE SET
                    step_name = EXCLUDED.step_name,
                    description = EXCLUDED.description,
                    step_order = EXCLUDED.step_order
            """, (
                config_id,
                step.get('id'),
                step.get('name'),
                step.get('description'),
                step.get('order', 0),
                step.get('is_mandatory', True),
                step.get('can_skip', False),
                Json(step.get('skip_conditions')) if step.get('skip_conditions') else None,
                step.get('icon')
            ))
        
        return len(steps)
    
    def _insert_fields(self, config_id: int, fields: Dict[str, Dict]) -> int:
        """Insert form fields"""
        if not fields:
            return 0
        
        count = 0
        for field_id, field_data in fields.items():
            self.execute("""
                INSERT INTO form_fields 
                (config_id, step_id, field_id, field_label, field_type, is_mandatory,
                 validation, options, examples, tips, extract_keywords, 
                 auto_formats, auto_clean, default_value, field_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (config_id, field_id) DO UPDATE SET
                    field_label = EXCLUDED.field_label,
                    field_type = EXCLUDED.field_type
            """, (
                config_id,
                field_data.get('step'),
                field_id,
                field_data.get('label', field_id),
                field_data.get('type', 'text'),
                field_data.get('is_mandatory', False),
                Json(field_data.get('validation')) if field_data.get('validation') else None,
                Json(field_data.get('options')) if field_data.get('options') else None,
                field_data.get('examples'),
                field_data.get('tips'),
                field_data.get('extract_keywords'),
                Json(field_data.get('auto_formats')) if field_data.get('auto_formats') else None,
                field_data.get('auto_clean', False),
                field_data.get('default'),
                count
            ))
            count += 1
        
        return count
    
    def _insert_messages(self, config_id: int, messages: Dict, prefix: str = "") -> int:
        """Insert messages recursively"""
        count = 0
        
        for key, value in messages.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                count += self._insert_messages(config_id, value, full_key)
            else:
                self.execute("""
                    INSERT INTO form_messages (config_id, message_key, message_template, language)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (config_id, message_key, language) DO UPDATE SET
                        message_template = EXCLUDED.message_template
                """, (config_id, full_key, str(value), 'id'))
                count += 1
        
        return count
    
    def _insert_commands(self, config_id: int, commands: Dict) -> int:
        """Insert commands"""
        if not commands:
            return 0
        
        count = 0
        for cmd_name, cmd_data in commands.items():
            keywords = cmd_data.get('keywords', [])
            pattern = cmd_data.get('pattern')
            
            self.execute("""
                INSERT INTO form_commands (config_id, command_name, keywords, pattern)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (config_id, command_name) DO UPDATE SET
                    keywords = EXCLUDED.keywords,
                    pattern = EXCLUDED.pattern
            """, (config_id, cmd_name, keywords, pattern))
            count += 1
        
        return count
    
    def _insert_default_triggers(self) -> int:
        """Insert default auto triggers"""
        triggers = [
            {
                "name": "idle_reminder",
                "type": "idle",
                "conditions": {"idle_minutes": 5},
                "message": "Hai! Sepertinya kamu sedang sibuk. Jangan lupa lanjutkan pendaftaran ya! 😊\n\nKamu sudah mengisi {completion}% data.",
                "priority": 10,
                "max_triggers": 2,
                "cooldown": 10
            },
            {
                "name": "document_stuck",
                "type": "step_stuck",
                "conditions": {"step": "documents", "stuck_minutes": 10},
                "message": "Butuh bantuan upload dokumen? 📄\n\nKamu bisa upload beberapa file sekaligus!",
                "priority": 8,
                "max_triggers": 1,
                "cooldown": 15
            },
            {
                "name": "incomplete_reminder",
                "type": "incomplete",
                "conditions": {"completion_below": 50, "idle_minutes": 15},
                "message": "Data pendaftaran kamu baru {completion}% lengkap.\n\nYuk selesaikan! Ketik 'lanjut' untuk melanjutkan. 💪",
                "priority": 5,
                "max_triggers": 1,
                "cooldown": 30
            },
            {
                "name": "rating_after_complete",
                "type": "rating_prompt",
                "conditions": {"after_completion": True},
                "message": "Terima kasih telah menyelesaikan pendaftaran! 🎉\n\nBoleh minta rating? Ketik angka 1-5 ⭐",
                "priority": 15,
                "max_triggers": 1,
                "cooldown": 60
            }
        ]
        
        count = 0
        for t in triggers:
            try:
                self.execute("""
                    INSERT INTO auto_triggers 
                    (trigger_name, trigger_type, conditions, message_template, 
                     priority, max_triggers_per_session, cooldown_minutes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trigger_name) DO UPDATE SET
                        conditions = EXCLUDED.conditions,
                        message_template = EXCLUDED.message_template
                """, (
                    t["name"], t["type"], Json(t["conditions"]), t["message"],
                    t["priority"], t["max_triggers"], t["cooldown"]
                ))
                count += 1
            except Exception as e:
                print(f"   Warning: {e}")
        
        return count
    
    def _insert_rating_prompts(self) -> int:
        """Insert rating prompts"""
        prompts = [
            {
                "type": "post_registration",
                "conditions": {"after_completion": True},
                "message": "🌟 Bagaimana pengalaman kamu?\n\nBerikan rating 1-5:\n⭐1 Buruk | ⭐⭐2 Kurang | ⭐⭐⭐3 Cukup | ⭐⭐⭐⭐4 Bagus | ⭐⭐⭐⭐⭐5 Sangat Bagus"
            },
            {
                "type": "idle_exit",
                "conditions": {"idle_minutes": 30},
                "message": "Sebelum pergi, boleh berikan rating? Ketik 1-5 ⭐"
            }
        ]
        
        count = 0
        for p in prompts:
            try:
                self.execute("""
                    INSERT INTO rating_prompts (prompt_type, conditions, prompt_message)
                    VALUES (%s, %s, %s)
                """, (p["type"], Json(p["conditions"]), p["message"]))
                count += 1
            except:
                pass
        
        return count
    
    def _insert_system_settings(self) -> int:
        """Insert system settings"""
        settings = [
            {
                "key": "form_config_source",
                "value": {"source": "database", "fallback": "yaml", "auto_sync": True},
                "desc": "Source for form configuration"
            },
            {
                "key": "idle_detection",
                "value": {"enabled": True, "check_interval_seconds": 60, "default_idle_minutes": 5},
                "desc": "Idle detection settings"
            },
            {
                "key": "rating_system",
                "value": {"enabled": True, "prompt_after_completion": True},
                "desc": "Rating system settings"
            },
            {
                "key": "multiple_upload",
                "value": {"enabled": True, "max_files": 10, "max_batch_size_mb": 50},
                "desc": "Multiple upload settings"
            }
        ]
        
        count = 0
        for s in settings:
            try:
                self.execute("""
                    INSERT INTO system_settings (setting_key, setting_value, description)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (setting_key) DO UPDATE SET
                        setting_value = EXCLUDED.setting_value,
                        updated_at = CURRENT_TIMESTAMP
                """, (s["key"], Json(s["value"]), s["desc"]))
                count += 1
            except:
                pass
        
        return count


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Population Tool")
    parser.add_argument("--verify", action="store_true", help="Verify table counts")
    parser.add_argument("--populate", type=str, help="Path to form_config.yaml")
    parser.add_argument("--force", action="store_true", help="Clear existing data first")
    parser.add_argument("--show", action="store_true", help="Show active config details")
    
    args = parser.parse_args()
    
    try:
        db = DatabasePopulator()
        
        if args.verify or (not args.populate and not args.show):
            print("\n📊 Table Verification:")
            print("-" * 40)
            counts = db.verify_tables()
            for table, count in counts.items():
                status = "✅" if isinstance(count, int) and count > 0 else "❌"
                print(f"  {status} {table}: {count}")
        
        if args.show:
            db.show_config_data()
        
        if args.populate:
            db.populate_from_yaml(args.populate, force=args.force)
        
        db.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()