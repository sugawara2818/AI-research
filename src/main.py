from reporter import AINewsReporter
from line_notifier import LineNotifier

def main():
    print("=== AI News Autonomous Reporter Starting ===")
    
    # Initialize components
    reporter = AINewsReporter()
    notifier = LineNotifier()
    
    # 1. Search for news
    news_items = reporter.search_news()
    
    if not news_items:
        print("No news found today. Skipping notification.")
        return
    
    # 2. Synthesize report
    report = reporter.synthesize_report(news_items)
    
    # 3. Notify via LINE
    if report:
        print("\n--- Final Report Preview ---")
        print(report)
        print("----------------------------\n")
        
        success = notifier.notify(report)
        if success:
            print("Process completed successfully.")
        else:
            print("Process failed at notification stage.")
    else:
        print("Failed to generate report.")

if __name__ == "__main__":
    main()
