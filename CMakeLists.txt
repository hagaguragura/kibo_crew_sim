cmake_minimum_required(VERSION 3.8)
project(llm_humanoid)

find_package(ament_cmake REQUIRED)

install(DIRECTORY
  scripts
  config
  DESTINATION share/${PROJECT_NAME})

ament_package()
