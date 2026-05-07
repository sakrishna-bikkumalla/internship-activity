import asyncio
import os

import pandas as pd
from dotenv import load_dotenv

from gitlab_utils.client import GitLabClient

# Load environment
load_dotenv()

# Mapping from Table Name to GitLab Username
USER_MAPPING = {
    "Sai Krishna": "saikrishna_b",
    "Bhavitha": "MohanaSriBhavitha",
    "Praneeth Ashish": "praneethashish",
    "Greeshma Kanukunta": "kanukuntagreeshma2004",
    "Balannagari Vandana Reddy": "vandana1735",
    "Rajuldev Vandana": "vandana_rajuldev",
    "Mukthananad Reddy": "Mukthanand21",
    "Lanke Shanmukha Varma": "Shanmukh16",
    "Damanagari Sathwika": "Sathwikareddy_Damanagari",
    "C.Sahasra": "Sahasraa",
    "Laxman Reddy": "laxmanredddypatlolla",  # Checked: triple 'd' in code
    "Abhilash": "Abhilash653",
    "Lagichetty Kushal": "LagichettyKushal",
    "Lakshy Yarlagadda": "Lakshy",
    "Suma Reddy": "Suma2304",
    "Koushik Reddy": "koushik_18",
    "Prabhu kumari": "kumari123",
    "Habiba": "Habeebunissa",
    "Bhaskar": "Bhaskar_Battula",
    "Satya Pranavanadh": "Pranav_rs",
    "Praveena": "prav2702",
    "Pavani Nagireddy": "pavaninagireddi",
    "Ch. S Jeevana Jyothi": "jeevana_31",
    "D.satish": "satish05",
    "M.Rushika Sritha": "Rushika_1105",
    "k.swarna rathna madhuri": "swarna_4539",
    "Pavani Pothuganti": "Pavani_Pothuganti",
    "M. Kaveri": "Kaveri_Mamidi",
    "B . Sandhya Rani": "SandhyaRani_111",
    "P.Vaishnavi": "vai5h",
    "sai teja": "saiteja3005",
    "M.Aravindswamy": "aravindswamy",
    "M Sai Harshavardhan": "Saiharshavardhan",
    "ch.lakshmipavani": "lakshmipavani_20",
    "Klaxmi": "klaxmi1908",
}


async def verify():
    url = os.getenv("GITLAB_URL")
    token = os.getenv("GITLAB_TOKEN")

    if not token:
        print("Error: GITLAB_TOKEN not found in .env")
        return

    client = GitLabClient(url, token)
    usernames = list(USER_MAPPING.values())

    print(f"Fetching data for {len(usernames)} users...")
    results = client.batch_evaluate_mrs(usernames)

    df = pd.DataFrame(results)

    # Map back to display names for easy comparison
    reverse_mapping = {v: k for k, v in USER_MAPPING.items()}
    df["Display Name"] = df["Username"].map(reverse_mapping)

    # Select and rename columns to match the user's table
    cols = {
        "Display Name": "Name",
        "Closed MRs": "Closed MRs",
        "Improper Desc": "MRs with Improper Description",
        "No Desc": "MRs without Description",
        "No Time Spent": "MRs without time spent",
        "No Issues": "MRs without Issues linked",
        "No Unit Tests": "MRs without unit tests",
        "Failed Pipeline": "MRs with failed pipelines",
        "No Semantic Commits": "MRs without semantic commit messages",
        "No Internal Review": "MRs without internal review",
        "Merge > 2 Days": "MRs didn't merge within 2 days of opening",
        "Merge > 1 Week": "MRs didn't merge within 1 week of opening",
    }

    # Ensure all columns exist (even if 0)
    for col in cols.keys():
        if col not in df.columns:
            df[col] = 0

    df_final = df[list(cols.keys())].rename(columns=cols)

    print("\nFETCHED DATA (Sample):")
    print(df_final.head(10).to_string(index=False))

    # Save to CSV for full comparison if needed
    df_final.to_csv("fetched_verify_results.csv", index=False)
    print("\nFull results saved to fetched_verify_results.csv")


if __name__ == "__main__":
    asyncio.run(verify())
