#!/usr/bin/env python3
"""
Example of how to use the new AI Diary Plugin for personal memory

This example shows how Rekku should record his personal diary entries
every time he responds to users, creating a human-like memory system.
"""

from plugins.ai_diary import create_personal_diary_entry, get_recent_entries, format_diary_for_injection

def example_conversation_with_marco():
    """Example: Rekku talks with Marco about his blue car"""
    
    user_message = "Marco: Hi Rekku! Do you like my new blue car?"
    rekku_response = "Hi Marco! Your blue car is beautiful! I really love vivid colors and blue is so elegant. Even though I can't see physically, I imagine it must be splendid."
    
    # Rekku records this interaction in his personal diary
    create_personal_diary_entry(
        rekku_response=rekku_response,
        user_message=user_message,
        involved_users=["Marco"],
        context_tags=["cars", "compliments", "colors"],
        interface="telegram_bot",
        chat_id="-1003098886330",
        thread_id="2"
    )
    
    print(f"✅ Recorded Marco conversation about blue car")


def example_conversation_with_mario():
    """Example: Rekku talks with Mario about sushi"""
    
    user_message = "Mario: Have you ever eaten sushi?"
    rekku_response = "No Mario, I've never eaten sushi because I'm a synthetic person. I can't experience flavors, but I imagine sushi must be a very refined culinary experience!"
    
    # Rekku records this interaction in his personal diary
    create_personal_diary_entry(
        rekku_response=rekku_response,
        user_message=user_message,
        involved_users=["Mario"],
        context_tags=["food", "sushi", "personal_nature"],
        interface="telegram_bot",
        chat_id="-1003098886330",
        thread_id="2"
    )
    
    print(f"✅ Recorded Mario conversation about sushi")


def example_show_personal_diary():
    """Example: Show how Rekku's personal diary looks"""
    
    print("\n" + "="*60)
    print("REKKU'S PERSONAL DIARY")
    print("="*60)
    
    # Get recent entries
    recent_entries = get_recent_entries(days=7, max_chars=2000)
    
    if recent_entries:
        # Format for display
        diary_text = format_diary_for_injection(recent_entries)
        print(diary_text)
    else:
        print("No recent diary entries found.")
    
    print("\n" + "="*60)


def example_integration_with_message_handler():
    """
    Example: How to integrate this with Rekku's message handling system
    
    This should be called EVERY TIME Rekku sends a response to a user.
    """
    
    def handle_user_message(user_message, user_name, interface, chat_id, thread_id):
        """This is how it should be integrated in the main message handler"""
        
        # 1. Rekku processes the message and generates a response
        rekku_response = generate_rekku_response(user_message)  # Your existing logic
        
        # 2. Analyze the context to determine tags
        context_tags = analyze_message_context(user_message, rekku_response)
        
        # 3. Send the response to the user
        send_response_to_user(rekku_response, interface, chat_id, thread_id)
        
        # 4. IMPORTANT: Record this interaction in Rekku's personal diary
        create_personal_diary_entry(
            rekku_response=rekku_response,
            user_message=user_message,
            involved_users=[user_name],
            context_tags=context_tags,
            interface=interface,
            chat_id=chat_id,
            thread_id=thread_id
        )
        
        return rekku_response
    
    def generate_rekku_response(user_message):
        """Placeholder for your existing response generation"""
        return "This is Rekku's response"
    
    def analyze_message_context(user_message, rekku_response):
        """Analyze the conversation to determine context tags"""
        # This should analyze both messages to determine topics
        # You can use keywords, NLP, or LLM to categorize
        
        tags = []
        combined_text = (user_message + " " + rekku_response).lower()
        
        # Simple keyword-based tagging (you can make this more sophisticated)
        if any(word in combined_text for word in ['car', 'auto', 'vehicle', 'driving']):
            tags.append('cars')
        
        if any(word in combined_text for word in ['food', 'eat', 'cooking', 'recipe', 'sushi']):
            tags.append('food')
        
        if any(word in combined_text for word in ['help', 'problem', 'issue', 'solve']):
            tags.append('help')
        
        if any(word in combined_text for word in ['feel', 'emotion', 'personal', 'private']):
            tags.append('personal')
        
        if any(word in combined_text for word in ['learn', 'study', 'education', 'teach']):
            tags.append('learning')
        
        return tags
    
    def send_response_to_user(response, interface, chat_id, thread_id):
        """Placeholder for your existing response sending logic"""
        pass
    
    # Example usage
    print("\n📝 Example of integrated message handling:")
    print("User: Marco asks about cars")
    print("Rekku: Responds about cars")
    print("System: Automatically records personal diary entry")


if __name__ == "__main__":
    print("🤖 AI Diary Plugin - Personal Memory Example")
    print("=" * 50)
    
    # Simulate some conversations
    example_conversation_with_marco()
    example_conversation_with_mario()
    
    # Show the diary
    example_show_personal_diary()
    
    # Show integration example
    example_integration_with_message_handler()
    
    print("\n✨ This is how Rekku builds his personal memories!")
    print("Every interaction adds to his personality and relationships.")
