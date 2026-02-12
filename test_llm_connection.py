
import os
import sys
import time
import requests
import config
from llm_client import LLMClient

def check_network():
    print(f"[*] Checking network connectivity to {config.BASE_URL}...")
    try:
        response = requests.get(config.BASE_URL, timeout=10)
        print(f"[+] Network check passed. Status code: {response.status_code}")
    except Exception as e:
        print(f"[-] Network check failed: {e}")

def get_current_ip():
    try:
        ip = requests.get('https://api.ipify.org', timeout=5).text
        print(f"[*] Current Public IP: {ip}")
    except:
        print("[-] Could not determine public IP")

def test_model(client, model_name, prompt):
    print(f"\n[*] Testing model: {model_name}")
    start_time = time.time()
    try:
        # Use simple query with json_mode=False for raw text
        response = client.query(
            "You are a helpful assistant.", 
            prompt, 
            json_mode=False, 
            model=model_name
        )
        duration = time.time() - start_time
        print(f"[+] Success! Duration: {duration:.2f}s")
        print(f"Response: {response[:100]}...")
        return True
    except Exception as e:
        duration = time.time() - start_time
        print(f"[-] Failed after {duration:.2f}s")
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("=== LLM Connection Diagnostic Tool ===\n")
    
    get_current_ip()
    check_network()
    
    client = LLMClient()
    print(f"\nLoaded Config:")
    print(f"API Key: {client.api_key[:4]}...{client.api_key[-4:] if client.api_key else 'None'}")
    print(f"Base URL: {client.base_url}")
    print(f"Default Model: {client.model}")
    print(f"Reasoner Model: {config.REASONER_MODEL}")

    # Test 1: Default Chat Model (fast)
    print("\n--- Test 1: Chat Model ---")
    if not test_model(client, client.model, "Say 'Hello'"):
        print("[-] Chat model failed. Aborting further tests.")
        sys.exit(1)

    # Test 2: Reasoner Model (slow)
    print("\n--- Test 2: Reasoner Model ---")
    reasoner_success = test_model(client, config.REASONER_MODEL, "Calculate 25 * 25 and explain step by step.")
    
    if reasoner_success:
        print("\n[+] All tests passed. LLM connection appears stable.")
    else:
        print("\n[-] Reasoner model failed. Only chat model is working.")
        print("Suggestion: Check if your API key supports this model or if timeout is too short.")
