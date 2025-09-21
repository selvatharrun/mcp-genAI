from vertexai.generative_models import GenerativeModel
import vertexai
from google.cloud import aiplatform
import os


PROJECT_ID = "sodium-coil-470706-f4"
LOCATION = "us-central1"

vertexai.init(project=PROJECT_ID, location=LOCATION)

model = GenerativeModel("gemini-2.5-flash-lite")

def find_precedents(user_clause: str, location: str = "US") -> str:
    """
    Find relevant legal precedents for a given clause and jurisdiction.
    
    Args:
        user_clause (str): The legal clause to analyze
        location (str): The jurisdiction (e.g., "US", "California", "India", "UK", "EU")
    
    Returns:
        str: Formatted text containing relevant legal precedents
    """
    try:
        # Validate inputs
        if not user_clause or not user_clause.strip():
            return "Error: No clause provided for analysis."
        
        if not location or not location.strip():
            location = "US"
        
        # Clean inputs
        user_clause = user_clause.strip()
        location = location.strip()
        
        prompt = f"""
        You are a highly precise legal research assistant with expertise in case law and legal precedents.
        
        Given the clause below, identify the most relevant and authoritative legal precedents from the specified jurisdiction.
        
        INSTRUCTIONS:
        - Focus primarily on the specified jurisdiction: "{location}"
        - If the location is a specific state (e.g., California, New York), prioritize state-specific cases but also include relevant federal precedents
        - If the location is a country (e.g., US, India, UK), include the most significant national and high court precedents
        - Only include precedents that are directly relevant to the legal principles in the clause
        - Prioritize landmark cases and frequently cited precedents
        - Exclude cases that are merely tangentially related
        
        For each precedent, provide:
        1. **Case Name** (with official citation if available)
        2. **Year** of decision
        3. **Court/Jurisdiction** (specify court level and jurisdiction)
        4. **Relevance** (2-3 sentences explaining the direct connection to the clause)
        5. **Key Principle** (the specific legal principle established)
        
        Format your response as a numbered list with clear sections for each precedent.
        
        **Legal Clause to Analyze:**
        "{user_clause}"
        
        **Target Jurisdiction:** {location}
        """

        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text.strip()
        else:
            return f"No precedents could be identified for the given clause in jurisdiction: {location}"
            
    except Exception as e:
        return f"Error analyzing precedents: {str(e)}"
