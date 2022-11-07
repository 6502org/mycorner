
# default build target
all: clean build

clean:
	rm -rf ./build/*

build:
	python3 build.py

.PHONY: clean build
