from core.conversation_manager import ConversationManager


def main() -> None:
    conversation = ConversationManager(max_messages=4)

    conversation.add_user_message("Open Blender.")

    conversation.add_assistant_message(
        "I'll open Blender."
    )

    conversation.add_tool_result(
        "Opening Blender."
    )

    conversation.add_assistant_message(
        "Blender is open."
    )

    print("Conversation:")
    for message in conversation.get_messages():
        print(message)

    print()
    print("Message count:", len(conversation.get_messages()))

    conversation.clear()

    print("After clear:", conversation.get_messages())


if __name__ == "__main__":
    main()