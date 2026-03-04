## Step 1: Understanding the Problem

#### What does the problem ask for?
An agent which will
1. Pull data from monday
2. clean it
3. deal with missing data and incomplete records
4. query it
5. do analysis on it

#### Thoughts
##### User Query Parsing
- The agent should have a background context and should also have a good prompt which will make it understand the problem and break it down into feasible steps in it's policy. 
- At this step, the agent should first parse the problem where it will define
	- Questions that are needed to answer (simple questions)
	- Analysis that might be needed to get answers to any of those questions
	- Stepwise workflow to get all of this answered
	- 
- As the API is GraphQL, I can make my agent choose what all it needs for it's analysis. 
	- But a tough question that arises is, for handling data inconsistencies, I might need the whole dataset where I can understand the data inconsistencies in a better way and then later make decisions on whether I want to impute, or transform, or delete that datapoint etc. .
	- What if I build a hidden layer where the agent periodically pull the complete data and tries to understand the data format and nature and update it's own policy to give better answers next time there is a question. 
		- One Solution is pulling all the data and then doing analysis and then choosing what analysis to do. 

##### Data Pull
- I will assume that the datasets that were given to me are the only two data formats that will be on monday. So I don't have to make the agent capable of handling unknown/new datasets with new formats. 
- Monday uses GraphQL, so my agent can select which data it can pull and the load in a dataframe.
- Tough question would be, What happens if a question needs data from two separate datasets and they need to be merged in a certain manner to do further analysis. I'll have to make my agent do that as well and then verify it's own result. 
##### Handling Data Inconsistencies
- The data is going to have inconsistencies, and there is some level of expectation on how the data is - datapoints might not be independent so I'll have to investigate that well. 
	- Find inconsistencies
	- Investigate why it might be missing
	- Investigate if I can delete some data points or will I have to find a different way to deal with it. 
- A big challenge would understand what all problems can come and how I can make the agent capable to handle any type of these data inconsistencies. 
- I'll have to make a decision on how much autonomy do I want my agent to have, because depending on the range of possible errors I can restrict my agent's focus to improve on it's consistency and accuracy of response. Obviously, this would also involve creating validation scripts to make sure everything is right in the end. 
- I have to report any issues with the data to the user. 
##### Creating Ad-Hoc Analysis
- Once the agent has prepared the data, first it can do some preliminary analysis on the data and based on those results the agent and keep querying again and again till it finishes the analysis in a way that answer's the initial questions.  
- Based on the data structure, I can define a set of tools/analysis that will be useful to answer a certain type of questions. 
	- Will there be a finite set of analysis that can be done, or will the agent need a different unique type of analysis for every different situation.
##### Business Insights
- What does this line mean, "The agent should help prepare data for leadership updates".
- It might mean that the agent should understand who is the user and what they want. So depending on that they the agent should decide what data to pull. 
##### Tech Stack
- I can use streamlit for the webapp. 
	- Will I hit any type limitation in it?
- Should I use LangGraph to make things easy or raw code everything?
##### Chatbot
- My chatbot will need a persistent memory to remember the chain of conversation, so I need to handle it in some way. 
#### Core goal
- My goal is to create a MVP which actually works and not a full fledged system because I have time limitations. So I need to be focused on fulfilling the core goals in the simplest way possible. 

## Time Log
- 10:30 - 12:00 : Understanding the problem and brainstorming about ideas.