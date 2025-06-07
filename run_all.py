# run_all.py
import subprocess
import sys
import os

# Define the sequence of scripts to run
# These should be in the same directory as run_all.py
scripts_to_run = [
    'partner_portal_invoice_count.py',
    'reportcount.py',
    'send.py',
]

def run_script(script_name):
    """
    Runs a Python script using subprocess and captures its output.
    Returns True if the script succeeds, False otherwise.
    """
    print(f"--- Running {script_name} ---")
    # Use sys.executable to ensure the correct Python environment is used
    # text=True decodes stdout/stderr as text using default encoding
    process = subprocess.Popen(
        [sys.executable, script_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1 # Line-buffered output for real-time printing
    )

    # Print output in real-time
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print(output.strip()) # strip() to remove extra newlines

    # Capture any remaining stderr
    stderr = process.stderr.read()
    if stderr:
        print(f"--- Errors from {script_name} ---", file=sys.stderr)
        print(stderr.strip(), file=sys.stderr) # strip() to remove extra newlines

    return_code = process.wait() # Wait for the process to finish and get the exit code

    if return_code != 0:
        print(f"--- {script_name} failed with exit code {return_code} ---", file=sys.stderr)
        return False
    else:
        print(f"--- {script_name} completed successfully ---")
        return True

def main():
    """
    Orchestrates the sequential execution of the defined scripts,
    continuing even if a script fails. Reports overall success/failure at the end.
    """
    print("--- Starting Daily Report Automation Workflow ---")

    overall_success = True # Assume success initially
    script_results = {} # Dictionary to store results of each script

    for script in scripts_to_run:
        success = run_script(script)
        script_results[script] = success # Store the result
        if not success:
            overall_success = False # If any script fails, mark overall as false

    print("\n--- Workflow Summary ---")
    for script, success in script_results.items():
        status = "SUCCESS" if success else "FAILED"
        print(f"  {script}: {status}")
    print("----------------------")

    if overall_success:
        print("--- All scripts completed without errors ---")
        sys.exit(0) # Exit with zero code for overall success
    else:
        print("--- Workflow finished with some failures ---", file=sys.stderr)
        sys.exit(1) # Exit with a non-zero code for overall failure

if __name__ == "__main__":
    main()