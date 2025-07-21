#!/bin/bash

remove_pycache() {
    local dir="$1"
    
    find "$dir/.." -type d -name '__pycache__' -exec rm -r {} +
}

# Default to the current directory if no argument is given
dir="${1:-.}"
remove_pycache "$dir"
