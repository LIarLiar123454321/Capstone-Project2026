from models.task import Task
from agent.parser import parse_task
from agent.mock_llm import mock_llm_response
from pydantic import ValidationError
from agent.executor import excexute_tool

try:
    user_input = "明天早上去健身房運動一小時，下午去圖書館讀書兩小時。"

    llm_response = mock_llm_response(user_input)
    result = parse_task(llm_response)

    print("解析結果：")
    print(result.model_dump())

    for task in result.tasks:
        print(f"任務：{task.name}")
        print(f"類型：{task.category}")
        print(f"地點：{task.location}")
        print(f"時間：{task.duration_minutes} 分鐘")
        print(f"預定日期：{task.date}")
        print(f"偏好：{task.time_preference}")
        print(f"優先程度：{task.priority}")
        print(f"截止日期：{task.deadline}")
        print("------------")
    
    if result.clarification_needed:
        print(f"還需要補充資訊：\n{result.missing_information}")

except ValidationError as e:
    print("任務資料有誤：")
    print(e.errors())

 #測試 print(excexute_tool("unknown_tool"))

