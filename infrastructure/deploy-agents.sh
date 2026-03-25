#!/bin/bash

STACK_OPERATION=$1

if [[ "$STACK_OPERATION" == "Create" || "$STACK_OPERATION" == "Update" ]]; then
    # deploy / update workshop resources
    echo "Hello"
elif [ "$STACK_OPERATION" == "Delete" ]; then
    # delete workshop resources
    echo "Goodbye"
else
    echo "Invalid stack operation!"
    exit 1
fi