# core/enhanced_prompt_generator.py
"""
Enhanced prompt generation with mandatory interface field emphasis.
"""

from typing import Dict, Any, List
import json
from core.logging_utils import log_debug, log_info


class EnhancedPromptGenerator:
    """Generates enhanced prompt instructions that emphasize the interface field."""
    
    @staticmethod
    def generate_action_examples_block(actions_block: Dict[str, Any]) -> str:
        """Generate a comprehensive examples block with mandatory interface fields."""
        
        if not actions_block:
            return ""
            
        examples_text = """
🚨 MANDATORY ACTION FORMAT - INTERFACE FIELD IS REQUIRED 🚨

EVERY action MUST include the "interface" field. Here are ALL available action types with CORRECT examples:

"""
        
        action_instructions = actions_block.get("action_instructions", {})
        available_actions = actions_block.get("available_actions", {})
        
        for action_type, interfaces_dict in action_instructions.items():
            examples_text += f"\n📋 ACTION TYPE: '{action_type}'\n"
            examples_text += "=" * 50 + "\n"
            
            for interface_id, instruction_data in interfaces_dict.items():
                examples_text += f"\n✅ INTERFACE: '{interface_id}'\n"
                
                # Get the example payload
                example_payload = instruction_data.get("payload", {})
                
                # Ensure interface is present in the example
                if "interface" not in example_payload:
                    example_payload = example_payload.copy()
                    
                # Create the complete action example
                complete_example = {
                    "type": action_type,
                    "interface": interface_id,  # ← ALWAYS PRESENT
                    "payload": example_payload
                }
                
                # Format as JSON
                example_json = json.dumps(complete_example, indent=2, ensure_ascii=False)
                examples_text += f"```json\n{example_json}\n```\n"
                
                # Add description if available
                description = instruction_data.get("description", "")
                if description:
                    examples_text += f"Description: {description}\n"
                
                # Add field requirements from available_actions
                if action_type in available_actions:
                    action_info = available_actions[action_type]
                    if interface_id in action_info.get("interfaces", {}):
                        interface_info = action_info["interfaces"][interface_id]
                        required_fields = interface_info.get("required_fields", [])
                        optional_fields = interface_info.get("optional_fields", [])
                        
                        if required_fields:
                            examples_text += f"Required payload fields: {', '.join(required_fields)}\n"
                        if optional_fields:
                            examples_text += f"Optional payload fields: {', '.join(optional_fields)}\n"
                
                examples_text += "\n"
        
        examples_text += """
🚨 CRITICAL REMINDERS:
1. ALWAYS include "interface": "interface_name" in every action
2. NEVER omit the "interface" field - actions will fail without it
3. Use the EXACT interface names shown above
4. The "interface" field goes at the TOP LEVEL, not inside payload

❌ WRONG (missing interface):
{
  "type": "message",
  "payload": {"text": "hello"}
}

✅ CORRECT (has interface):
{
  "type": "message", 
  "interface": "telegram",
  "payload": {"text": "hello"}
}

"""
        
        return examples_text
    
    @staticmethod
    def inject_interface_warnings_in_prompt(base_prompt: str) -> str:
        """Inject additional interface warnings throughout the prompt."""
        
        interface_reminders = [
            "\n🚨 REMEMBER: Every action needs \"interface\" field! 🚨\n",
            "\n⚠️ Don't forget the \"interface\" field in your actions! ⚠️\n",
            "\n📝 Action checklist: type ✓, interface ✓, payload ✓\n"
        ]
        
        # Inject reminders at strategic points
        enhanced_prompt = base_prompt
        
        # Add at the beginning
        enhanced_prompt = interface_reminders[0] + enhanced_prompt
        
        # Add in the middle if the prompt is long enough
        if len(enhanced_prompt) > 1000:
            middle_point = len(enhanced_prompt) // 2
            enhanced_prompt = (enhanced_prompt[:middle_point] + 
                             interface_reminders[1] + 
                             enhanced_prompt[middle_point:])
        
        # Add at the end
        enhanced_prompt = enhanced_prompt + interface_reminders[2]
        
        return enhanced_prompt


def enhance_actions_block_with_examples(actions_block: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance the actions block with detailed examples emphasizing interface fields."""
    
    if not actions_block:
        return actions_block
        
    enhanced_block = actions_block.copy()
    
    # Generate the enhanced examples text
    examples_text = EnhancedPromptGenerator.generate_action_examples_block(actions_block)
    
    # Add to the block
    enhanced_block["enhanced_examples"] = examples_text
    enhanced_block["interface_enforcement_mode"] = True
    
    log_debug("[enhanced_prompt_generator] Enhanced actions block with interface examples")
    
    return enhanced_block
