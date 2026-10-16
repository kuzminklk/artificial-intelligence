# Edit terminal variables
nano ~/.bashrc

# Run “clang-format” for all files down in the directory
git ls-files '*.c' '*.h' | xargs clang-format -i
