from core.tool_router import ToolRouter


def hello_tool() -> str:
    return "Hello from a tool."


def main() -> None:
    router = ToolRouter()

    router.register("hello_tool", hello_tool)

    tool = router.get_tool("hello_tool")

    if tool is None:
        raise RuntimeError("Tool was not registered.")

    result = tool()

    print("Tool result:", result)
    print("Registered tools:", [tool.__name__ for tool in router.get_tools()])


if __name__ == "__main__":
    main()