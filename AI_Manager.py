import pandas as pd
import json
from ollama import chat




def Generate_Resume_Scores(Prompt):
    try:
        df = pd.read_csv('resumes.csv')
    except FileNotFoundError:
        print("Error: resumes.csv not found.")
        exit()

    grades = []
    explanations = []

    for index, row in df.iterrows():
        resume_content = row['resume_text']
        
        prompt = f"""
        You are an expert technical recruiter. Evaluate the following resume strictly based on these requirements:
        - 3+ years of Python experience
        - Hands-on experience with Docker and containerization
        - Familiarity with AI/LLM models
        
        Resume text:
        {resume_content}
        """
        
        print(f"Evaluating resume {index + 1}...")
        
        response = chat(
            model='mistral',
            messages=[{'role': 'user', 'content': prompt}],
            format={
                "type": "object",
                "properties": {
                    "grade": {
                        "type": "integer",
                        "description": "Score from 1 to 10 based on how well they meet the requirements"
                    },
                    "explanation": {
                        "type": "string",
                        "description": "A 2-3 sentence explanation for the score"
                    }
                },
                "required": ["grade", "explanation"]
            },
            options={'temperature': 0.1}
        )
        
        evaluation = json.loads(response.message.content)
        
        grades.append(evaluation['grade'])
        explanations.append(evaluation['explanation'])
        
        print(f"Result: {evaluation['grade']}/10 - {evaluation['explanation']}\n")

    df['ai_grade'] = grades
    df['ai_explanation'] = explanations

    df.to_csv('graded_resumes.csv', index=False)
    print("Processing complete. Results saved to graded_resumes.csv")