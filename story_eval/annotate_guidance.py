# RUN: CUDA_VISIBLE_DEVICES=2,3,4 python -m story_eval.annotate_guidance

import time
import traceback
import pandas as pd
import guidance
from guidance import models, gen, select, user, system, assistant

def extract_dict(output, keys):
    return {k: output[k] for k in keys}

# Define annotation fn
@guidance
def annotate_psd(lm, persona, story, temperature=1):
    if persona:
        with system():
            lm += f"{persona}"
    with user():
        lm += f"""\
        ###Task Description: 
        1. Review the given components of psychological depth: authenticity, emotion provoking, empathy, engagement, and narrative complexity. Be sure to understand each concept and the questions that characterize them.
        2. Read a given story, paying special attention to components of psychological depth.
        3. Assign a rating for each component from 1 to 5. 1 is greatly below average, 3 is average and 5 is greatly above average (should be rare to provide this score).
        4. Lastly, estimate the likelihood that each story was authored by a human or an LLM. Think about what human or LLM writing characteristics may be. Assign a score from 1 to 5, where 1 means very likely LLM written and 5 means very likely human written. 

        ###Description of Psychological Depth Components:  
        
        We define sychological depth in terms of the following concepts, each illustrated by several questions: 

        - Authenticity 
            - Does the writing feel true to real human experiences? 
            - Does it represent psychological processes in a way that feels authentic and believable? 
        - Emotion Provoking 
            - How well does the writing depict emotional experiences? 
            - Does it explore the nuances of the characters' emotional states, rather than just describing them in simple terms? 
            - Can the writing show rather than tell a wide variety of emotions? 
            - Do the emotions that are shown in the text make sense in the context of the story? 
        - Empathy 
            - Do you feel like you were able to empathize with the characters and situations in the text? 
            - Do you feel that the text led you to introspection, or to new insights about yourself or the world?" 
        - Engagement 
            - Does the text engage you on an emotional and psychological level? 
            - Do you feel the need to keep reading as you read the text? 
        - Narrative Complexity 
            - Do the characters in the story have multifaceted personalities? Are they developed beyond stereotypes or tropes? Do they exhibit internal conflicts? 
            - Does the writing explore the complexities of relationships between characters? 
            - Does it delve into the intricacies of conflicts and their partial or complete resolutions? 

        ###The story to evaluate:
        {story}
        """
    with assistant():
        lm += f"""\
        Authenticity Score: {gen('authenticity_score', regex='[1-5]', temperature=temperature)}
        Emotion Provoking Score: {gen('emotion_provoking_score', regex='[1-5]', temperature=temperature)}
        Empathy Score: {gen('empathy_score', regex='[1-5]', temperature=temperature)}
        Engagement Score: {gen('engagement_score', regex='[1-5]', temperature=temperature)}
        Narrative Complexity Score: {gen('narrative_complexity_score', regex='[1-5]', temperature=temperature)}
        Human Likeness Score: {gen('human_likeness_score', regex='[1-5]', temperature=temperature)}
        """
    return lm

model_ids = [
    "/data2/.shared_models/llama.cpp_models/Meta-Llama-3-70B-Instruct-f16.gguf",
    "/data2/.shared_models/llama.cpp_models/Meta-Llama-3-8B-Instruct-f16.gguf",
]

# story_id,premise_id,premise,text,author_type,author_short,author_full,net_upvotes
dataset = pd.read_csv("./data/study_stories.csv", encoding='8859')

keys = [
    "authenticity_score",
    "emotion_provoking_score",
    "empathy_score",
    "engagement_score",
    "narrative_complexity_score",
    "human_likeness_score",
]

personas = [
    "You are a helpful AI who specializes in evaluating the psychological depth present in stories. In particular, you specialize in evaluating the genuineness and believability of characters, dialogue, and scenarios in stories.",
    "You are a helpful AI who specializes in evaluating the psychological depth present in stories. In particular, you focus on identifying and assessing moments in the narrative that effectively evoke empathetic connections with the characters.",
    "You are a helpful AI who specializes in evaluating the psychological depth present in stories. In particular, you evaluate how well a story captures and maintains the reader's interest through pacing, suspense, and narrative flow.",
    "You are a helpful AI who specializes in evaluating the psychological depth present in stories. In particular, you examine the text for its ability to provoke a wide range of intense emotional responses in the reader.",
    "You are a helpful AI who specializes in evaluating the psychological depth present in stories. In particular, you analyze the structural and thematic intricacy of the plot, character development, and the use of literary devices.",
]

# personas = [
#     "You are a helpful AI who specializes in evaluating the psychological depth present in stories.",
#     "You are a helpful AI who specializes in evaluating the psychological depth present in stories.",
#     "You are a helpful AI who specializes in evaluating the psychological depth present in stories.",
#     "You are a helpful AI who specializes in evaluating the psychological depth present in stories.",
#     "You are a helpful AI who specializes in evaluating the psychological depth present in stories.",
# ]

# personas = ["", "", "", "", ""]

temps = [0, 1]

for model_id in model_ids:

    # Load the model
    if "llama.cpp" in model_id.lower():
        # Assume Llama.cpp
        print("Using Llama.cpp!")
        llm = models.LlamaCpp(
            model=model_id,
            echo=False,
            n_gpu_layers=-1,
            n_ctx=3072
        )
        model_id = model_id.split("/")[-1].replace(".gguf", "")
    else:
        # Assume Transformers
        print("Using Transformers!")
        llm = models.Transformers(
            model_id, 
            echo=False,
            cache_dir="/data2/.shared_models/", 
            device_map='auto'
        )


    for t in temps:

        save_path = f"/data2/fabricehc/llm-psych-depth/human_study/data/processed/{model_id.replace('/', '--')}_annotations_mop_t={t}.csv"

        # Check if the save file already exists and load it
        try:
            existing_annotations = pd.read_csv(save_path)
        except FileNotFoundError:
            existing_annotations = pd.DataFrame()

        results = []

        for participant_id, persona in enumerate(personas):

            for index, row in dataset.iterrows():
                # Skip rows that have already been annotated
                if not existing_annotations.empty and ((existing_annotations["participant_id"] == participant_id) & (existing_annotations["story_id"] == row["story_id"]) & (existing_annotations["premise_id"] == row["premise_id"])).any():
                    print(f"Skipping already annotated row: participant_id={participant_id}, story_id={row['story_id']}, premise_id={row['premise_id']}")
                    continue

                story = row["text"]
                try:
                    start_time = time.time()
                    output = llm + annotate_psd(persona=persona, story=story, temperature=t)
                    time_taken = time.time() - start_time
                    output_dict = extract_dict(output, keys)
                    output_dict.update({
                        "participant_id": participant_id, 
                        "persona": persona, 
                        "time_taken": time_taken,
                        **row,
                    })
                    print(f"Results for participant_id={participant_id}, story_id={row['story_id']}, premise_id={row['premise_id']}': {output_dict}")
                    results.append(output_dict)
                except Exception:
                    print(traceback.format_exc())
                    print(f"Error on: participant_id={participant_id}, story_id={row['story_id']}, premise_id={row['premise_id']}, story={story}")

                # Append new results to existing annotations and save to CSV
                df = pd.DataFrame(results)
                combined_df = pd.concat([existing_annotations, df]).drop_duplicates(subset=["participant_id", "story_id", "premise_id"])
                combined_df.to_csv(save_path, index=False)

    # Delete previous llm to free up memory asap
    del llm