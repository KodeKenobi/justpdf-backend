"""
Fix the syntax error in campaign_sequential.py by moving the except block before the finally block.
"""

with open('campaign_sequential.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the problematic except block (should be around line 546)
# It needs to be moved before the finally block (around line 509)

# Strategy: Find the finally block, then find the except block after it, and swap them

finally_line = None
except_line = None
except_end_line = None

for i, line in enumerate(lines):
    # Look for the finally block that's part of the main try
    if '                    finally:' in line and finally_line is None:
        # Check if this is the right finally (around line 509)
        if i > 500 and i < 520:
            finally_line = i
            print(f"Found finally at line {i+1}: {line.strip()}")
    
    # Look for the except BaseException block after the finally
    if '                except BaseException as outer_err:' in line and except_line is None:
        if finally_line and i > finally_line:
            except_line = i
            print(f"Found except at line {i+1}: {line.strip()}")
            
            # Find where this except block ends (look for the next line at same or lower indentation)
            indent_level = len(line) - len(line.lstrip())
            for j in range(i+1, len(lines)):
                current_indent = len(lines[j]) - len(lines[j].lstrip())
                # If we find a line at the same or lower indentation level (and it's not empty), that's the end
                if lines[j].strip() and current_indent <= indent_level:
                    except_end_line = j - 1
                    print(f"Except block ends at line {except_end_line+1}")
                    break
            break

if finally_line and except_line and except_end_line:
    print(f"\nMoving except block (lines {except_line+1}-{except_end_line+1}) to before finally block (line {finally_line+1})")
    
    # Extract the except block
    except_block = lines[except_line:except_end_line+1]
    
    # Remove the except block from its current location
    new_lines = lines[:except_line] + lines[except_end_line+1:]
    
    # Insert the except block before the finally block
    # Adjust the finally_line index since we removed lines
    adjusted_finally_line = finally_line
    
    new_lines = new_lines[:adjusted_finally_line] + except_block + new_lines[adjusted_finally_line:]
    
    # Write the fixed file
    with open('campaign_sequential.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    print("\n✓ File fixed successfully!")
else:
    print(f"\n✗ Could not find the blocks to fix")
    print(f"  finally_line: {finally_line}")
    print(f"  except_line: {except_line}")
    print(f"  except_end_line: {except_end_line}")
