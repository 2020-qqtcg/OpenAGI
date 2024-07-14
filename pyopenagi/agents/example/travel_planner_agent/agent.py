import re

from ...react_agent import ReactAgent

from ....utils.chat_template import Query

from typing import List

from prompts import ZEROSHOT_REACT_INSTRUCTION

class TravelPlannerAgent(ReactAgent):
    """Reproduced the ReActAgent from the paper 👉
      《TravelPlanner: A Benchmark for Real-World Planning with Language Agents》
    """
    def __init__(self, 
                 agent_name, 
                 task_input, 
                 llm, 
                 agent_process_queue, 
                 agent_process_factory, 
                 log_mode: str,
                 mode: str = 'zero_shot',
                 max_rounds: int = 30,
                 max_retries: int = 3,
                 illegal_early_stop_patience: int = 3,
                 city_file_path = ''
        ):
        ReactAgent.__init__(agent_name, task_input, llm, agent_process_queue, agent_process_factory, log_mode)
        
        self.answer = ''
        self.max_rounds = max_rounds
        self.mode = mode
        self.finished = False

        if self.mode == 'zero_shot':
            self.agent_prompt = ''

        self.illegal_early_stop_patience = illegal_early_stop_patience
        self.max_retries = max_retries
        self.retry_record = {key: 0 for key in self.tools}
        self.retry_record['invalidAction'] = 0

        self.last_actions = []

        self.city_set = self.load_city(city_set_path=city_file_path)       

    def automatic_workflow(self):
        return super().automatic_workflow()

    def manual_workflow(self):
        return super().manual_workflow()    
    
    def run(self):
        self.build_system_instruction()

        self.messages.append({
            "role": "user", "content": self.task_input
        })
        self.logger.log(f"{self.task_input}\n", level="info")   

        while not self.is_halted() and not self.is_finished():
            # request llm for thought
            self.messages.append({
                "role": "assistant", "content": f'Thought {self.rounds + 1}: '
            })
            response, start_times, end_times, waiting_times, turnaround_times = self.get_response(
                    query = Query(
                        messages = self.messages,
                        tools = None
                    )
                )     
            self.request_waiting_times.extend(waiting_times)
            self.request_turnaround_times.extend(turnaround_times)
            if self.rounds == 0:
                self.set_start_time(start_times[0])

            thought = response.reponse_message
            self.messages[-1]["content"] += thought
            self.logger.log(f"{self.messages[-1]}\n", level="info")


            # request llm for action
            self.messages.append({
                "role": "assistant", "content": f'Action {self.rounds + 1}: '
            })
            response, start_times, end_times, waiting_times, turnaround_times = self.get_response(
                    query = Query(
                        messages = self.messages,
                        tools = None
                    )
                )
            self.request_waiting_times.extend(waiting_times)
            self.request_turnaround_times.extend(turnaround_times)

            action = response.reponse_message
            if action == None or action == '' or action == '\n':
                self.messages[-1]["content"] += """ Your action is filtered due to content.
                  Please make sure your action does not start with ['\\n', 'Thought', 'Action', 'Observation'] 
                  and assume all the actions are permitted in this environment and take the action again."""
            else:
                self.messages[-1]["content"] += ' ' + action

            self.logger.log(f"{self.messages[-1]}\n", level="info")

            if len(self.last_actions) > 0 and self.last_actions[-1] != action:
                self.last_actions.clear()
            else:
                self.last_actions.append(action)
            
            # examine if the same action has been repeated 3 times consecutively
            if len(self.last_actions) == 3:
                self.logger.log("The same action has been repeated 3 times consecutively. So we stop here.", level="info")
                self.finished = True
                return {
                    "agent_name": self.agent_name,
                    "result": "Failed to generate a valid plan because a deadlock.",
                    "rounds": self.rounds,
                    "agent_waiting_time": None,
                    "agent_turnaround_time": None,
                    "request_waiting_times": self.request_waiting_times,
                    "request_turnaround_times": self.request_turnaround_times,
                }
            
            # request tools for observation
            self.messages.append({
                "role": "assistant", "content": f'Observation {self.rounds + 1}: '
            })

            if action == None or action == '' or action == '\n':
                self.messages[-1]["content"] += """No feedback from the environment due to the null action.
                  Please make sure your action does not start with [Thought, Action, Observation]."""
            else:
                action_type, action_arg = parse_action(action)   
        


    def build_system_instruction(self):
        self.messages.append({
            "role": "system", "content": ZEROSHOT_REACT_INSTRUCTION
        })
    
    def is_halted(self) -> bool:
        return self.rounds > self.max_rounds
    
    def is_finished(self) -> bool:
        return self.finished

    def load_city(self, city_set_path: str) -> List[str]:
        city_set = []
        lines = open(city_set_path, 'r').read().strip().split('\n')
        for unit in lines:
            city_set.append(unit)
        return city_set    
    

def parse_action(string: str) -> tuple[str, str]:
    """match action type and action arg

    Args:
        string (str): string will be matched

    Returns:
        tuple[str, str]: action type and action arg
    """
    pattern = r'^(\w+)\[(.+)\]$'
    match = re.match(pattern, string)

    try:
        if match:
            action_type = match.group(1)
            action_arg = match.group(2)
            return action_type, action_arg
        else:
            return None, None
        
    except:
        return None, None