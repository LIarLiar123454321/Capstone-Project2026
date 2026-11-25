def mock_llm_response(user_input: str) -> dict:
    """
    將使用者輸入到llm。
    模擬 LLM 的輸出。
    """

    #模擬資料，LLM會回傳JSON，但暫時直接轉成python字典
    fake_llm_response = {
        "tasks":[
            {
                "name": "去健身房運動",
                "category": "excercise",
                "location": "健身房",
                "duration_minutes": 60,
                "date": "2026-11-25",
                "time_preference": "morning",
                "priority": "normal",
                "deadline": None
            },
            {
                "name": "去圖書館讀書",
                "category": "study",
                "location": "圖書館",
                "duration_minutes": 120,
                "date": "2026-11-25",
                "time_preference": "afternoon",
                "priority": "normal",
                "deadline": None
            },
            {
                "name": "吃飯",
                "category": "diet",
                "location": None,
                "duration_minutes": 30,
                "date": "2026-11-25",
                "time_preference": "evening",
                "priority": "high",
                "deadline": None
            }
        ],
        "missing_information": [],
        "clarification_needed": False
    }

    return fake_llm_response