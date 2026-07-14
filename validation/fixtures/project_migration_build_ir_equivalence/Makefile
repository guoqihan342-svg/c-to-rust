all: build/program

build/unit.o: src/unit.c
	clang -std=c11 -DVALUE=7 -c src/unit.c -o build/unit.o

build/program: build/unit.o
	clang build/unit.o -o build/program
