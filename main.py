from researcher import Researcher
from reporter import Reporter
from notifier import Notifier

def run_ai_research_system():
    print("--- Starting AI Research System ---")
    
    # 1. Research
    researcher = Researcher()
    search_results = researcher.search_news()
    facts = researcher.filter_and_extract_facts(search_results)
    
    # 2. Report
    reporter = Reporter()
    report = reporter.generate_report(facts)
    
    # 3. Notify
    notifier = Notifier()
    notifier.send_line_notification(report)
    
    print("--- AI Research System Completed ---")

if __name__ == "__main__":
    run_ai_research_system()
