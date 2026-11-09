# Edit terminal variables
nano ~/.bashrc

# Run “clang-format” for all files down in the directory
git ls-files '*.c' '*.h' | xargs clang-format -i

# Remove the file with sensitive information
shred -vzu -n 3 seed-phrases-encrypted.txt
