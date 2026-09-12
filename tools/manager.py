import logging
from typing import Dict, Any, Optional, Callable

from tools import (
    open_application,
    manage_reminder,
    execute_whitelisted_script,
    search_web,
    display_content,
    find_and_open_folder,
    open_web_target,
    playwright_navigate,
    playwright_extract_text,
    playwright_click,
    playwright_fill,
    playwright_screenshot,
    desktop_click,
    desktop_type,
    desktop_focus_window,
    desktop_locate_element,
    analyze_data_file,
    trim_media_file,
    set_system_volume,
    set_display_brightness,
    get_hardware_status,
    get_power_draw,
    shutdown_system,
    restart_system,
    sleep_system,
    create_and_save_file,
    open_target_item,
    grep_files,
    search_files_by_name,
    take_screenshot_sync,
    play_youtube_video_sync,
    capture_screen_base64,
    analyze_screen,
)

logger = logging.getLogger(__name__)


# List of expanded tool functions passed to Gemini / LLM models
REGISTERED_TOOLS = [
    open_application,
    find_and_open_folder,
    open_web_target,
    manage_reminder,
    execute_whitelisted_script,
    search_web,
    display_content,
    playwright_navigate,
    playwright_extract_text,
    playwright_click,
    playwright_fill,
    playwright_screenshot,
    desktop_click,
    desktop_type,
    desktop_focus_window,
    desktop_locate_element,
    analyze_data_file,
    trim_media_file,
    set_system_volume,
    set_display_brightness,
    get_hardware_status,
    get_power_draw,
    shutdown_system,
    restart_system,
    sleep_system,
    create_and_save_file,
    open_target_item,
    grep_files,
    search_files_by_name,
    take_screenshot_sync,
    play_youtube_video_sync,
    analyze_screen,
]



def execute_registered_tool(
    function_name: str,
    function_args: Dict[str, Any],
    action_callback: Optional[Callable[[str], None]] = None,
    display_callback: Optional[Callable[[str, str], None]] = None,
) -> str:
    """
    Routes and executes function calls requested by Gemini / Llama LLM tools.
    """
    args = function_args or {}
    logger.info(f"[Tool Manager] Executing '{function_name}' with args: {args}")

    def log_action(desc: str):
        if action_callback:
            try:
                action_callback(desc)
            except Exception as e:
                logger.warning(f"Action callback error: {e}")

    try:
        # 1. Base System & Application Tools
        if function_name == "open_application":
            res = open_application(app_name=args.get("app_name", ""))
            log_action(f"Opened {args.get('app_name', '').capitalize()}")
            return res

        elif function_name in ("grep_files", "grep_search_files", "content_search"):
            res = grep_files(
                query=args.get("query", ""),
                target_dir=args.get("target_dir", "Desktop"),
                file_extension=args.get("file_extension", None),
                max_results=int(args.get("max_results", 10)),
            )
            log_action(f"Grep search for '{args.get('query', '')}' in '{args.get('target_dir', 'Desktop')}'")
            return res

        elif function_name in ("search_files_by_name", "find_files_by_name", "file_name_search"):
            res = search_files_by_name(
                filename_pattern=args.get("filename_pattern", args.get("query", "")),
                target_dir=args.get("target_dir", "Desktop"),
                max_results=int(args.get("max_results", 10)),
            )
            log_action(f"File search for '{args.get('filename_pattern', args.get('query', ''))}'")
            return res

        elif function_name in ("create_and_save_file", "save_file", "create_file"):
            res = create_and_save_file(
                filepath=args.get("filepath", args.get("path", "")),
                content=args.get("content", ""),
                open_after_save=bool(args.get("open_after_save", True)),
            )
            log_action(f"Saved file to '{args.get('filepath', args.get('path', ''))}'")
            return res

        elif function_name in ("open_target_item", "open_file", "launch_file"):
            res = open_target_item(path_str=args.get("path_str", args.get("filepath", args.get("path", ""))))
            log_action(f"Opened target item '{args.get('path_str', args.get('filepath', args.get('path', '')))}'")
            return res

        elif function_name in ("set_system_volume", "set_volume", "change_volume"):
            res = set_system_volume(level=int(args.get("level", 50)))
            log_action(f"Set volume to {args.get('level', 50)}%")
            return res


        elif function_name in ("set_display_brightness", "set_brightness", "change_brightness"):
            res = set_display_brightness(level_percent=int(args.get("level_percent", args.get("level", 100))))
            log_action("Set display brightness")
            return res

        elif function_name in ("get_hardware_status", "hardware_status", "system_metrics"):
            res = get_hardware_status()
            log_action("Retrieved hardware status")
            return res

        elif function_name in ("get_power_draw", "power_draw", "get_voltage", "system_power"):
            res = get_power_draw()
            log_action("Retrieved power draw")
            return res

        elif function_name in ("shutdown_system", "shutdown"):
            res = shutdown_system(confirm=bool(args.get("confirm", False)))
            log_action("Initiated shutdown check")
            return res

        elif function_name in ("restart_system", "reboot"):
            res = restart_system(confirm=bool(args.get("confirm", False)))
            log_action("Initiated restart check")
            return res

        elif function_name in ("sleep_system", "sleep"):
            res = sleep_system()
            log_action("Initiated sleep mode")
            return res


        elif function_name in ("play_youtube_video", "play_youtube"):
            res = play_youtube_video_sync(search_query=args.get("search_query", args.get("query", "")))
            log_action(f"Playing YouTube video: '{args.get('search_query', args.get('query', ''))}'")
            return res

        elif function_name in ("take_screenshot", "capture_screenshot"):
            url = args.get("url", "")
            out_path = args.get("output_path", args.get("path", "screenshot.png"))
            res = take_screenshot_sync(url=url, output_path=out_path)
            log_action(f"Captured screenshot of '{url}'")
            return res



        elif function_name in ("open_system_folder", "find_and_open_folder"):
            res = find_and_open_folder(folder_name=args.get("folder_name", ""))
            log_action(f"Opened folder '{args.get('folder_name', '')}'")
            return res

        elif function_name in ("navigate_web", "open_web_target"):
            res = open_web_target(query_or_url=args.get("query_or_url", ""), platform=args.get("platform", "general"))
            log_action(f"Navigated web: '{args.get('query_or_url', '')}'")
            return res

        elif function_name == "manage_reminder":
            res = manage_reminder(
                action=args.get("action", ""),
                reminder_text=args.get("reminder_text", ""),
                time_str=args.get("time_str", ""),
            )
            log_action("Managed reminder")
            return res

        elif function_name == "execute_whitelisted_script":
            res = execute_whitelisted_script(script_name=args.get("script_name", ""))
            log_action(f"Executed script '{args.get('script_name', '')}'")
            return res

        elif function_name == "search_web":
            res = search_web(query=args.get("query", ""))
            log_action(f"Searched web for '{args.get('query', '')}'")
            return res

        elif function_name == "display_content":
            res = display_content(title=args.get("title", "Visual Display"), markdown_content=args.get("markdown_content", ""))
            log_action(f"Displayed: {args.get('title', '')}")
            if display_callback:
                try:
                    display_callback(args.get("title", ""), args.get("markdown_content", ""))
                except Exception:
                    pass
            return res

        # 2. Playwright Web Automation Tools
        elif function_name in ("playwright_navigate", "navigate_to_url"):
            res = playwright_navigate(url=args.get("url", ""))
            log_action(f"Playwright navigated: {args.get('url', '')}")
            return res

        elif function_name in ("playwright_extract_text", "extract_page_text"):
            res = playwright_extract_text()
            log_action("Extracted page text")
            return res

        elif function_name in ("playwright_click", "click_element"):
            res = playwright_click(selector=args.get("selector", ""))
            log_action(f"Clicked element: '{args.get('selector', '')}'")
            return res

        elif function_name in ("playwright_fill", "fill_form"):
            res = playwright_fill(selector=args.get("selector", ""), text=args.get("text", ""))
            log_action(f"Filled form element '{args.get('selector', '')}'")
            return res

        elif function_name in ("playwright_screenshot", "take_screenshot"):
            res = playwright_screenshot(path=args.get("path", None))
            log_action("Captured web screenshot")
            return res

        # 3. Desktop GUI & Game Automation Tools
        elif function_name in ("desktop_click", "click_at_coordinates"):
            res = desktop_click(x=args.get("x", 0), y=args.get("y", 0))
            log_action(f"Desktop click at ({args.get('x', 0)}, {args.get('y', 0)})")
            return res

        elif function_name in ("desktop_type", "type_keystrokes"):
            res = desktop_type(text=args.get("text", ""))
            log_action(f"Typed keystrokes: '{args.get('text', '')}'")
            return res

        elif function_name in ("desktop_focus_window", "focus_window"):
            res = desktop_focus_window(title=args.get("title", ""))
            log_action(f"Focused window '{args.get('title', '')}'")
            return res

        elif function_name in ("desktop_locate_element", "locate_element_on_screen"):
            res = desktop_locate_element(image_path=args.get("image_path", ""))
            log_action(f"Located template element '{args.get('image_path', '')}'")
            return res

        # 4. Data Processing & Media Tools
        elif function_name in ("analyze_data_file", "read_analyze_csv_excel"):
            res = analyze_data_file(file_path=args.get("file_path", ""))
            log_action(f"Analyzed data file '{args.get('file_path', '')}'")
            return res

        elif function_name in ("trim_media_file", "convert_trim_media"):
            res = trim_media_file(
                input_file=args.get("input_file", ""),
                output_file=args.get("output_file", ""),
                start_time=args.get("start_time", None),
                end_time=args.get("end_time", None),
            )
            log_action("Processed media file")
            return res

        elif function_name in ("analyze_screen", "describe_screen", "capture_screen"):
            prompt_str = args.get("prompt", "Describe what is currently visible on my screen in detail.")
            res = analyze_screen(prompt=prompt_str)
            log_action("Analyzed screen via Gemini Flash")
            return res

        else:

            msg = f"Unknown tool requested: '{function_name}'."
            logger.warning(msg)
            return msg

    except Exception as e:
        logger.error(f"Error executing tool '{function_name}': {e}")
        return f"Error executing tool '{function_name}': {str(e)}"


if __name__ == "__main__":
    print("[Tool Manager] Registered tools count:", len(REGISTERED_TOOLS))
