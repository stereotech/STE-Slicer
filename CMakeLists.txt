project(steslicer NONE)
cmake_minimum_required(VERSION 2.8.12)

set(CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake/
                      ${CMAKE_MODULE_PATH})

include(GNUInstallDirs)

set(URANIUM_DIR "${CMAKE_SOURCE_DIR}/../Uranium" CACHE DIRECTORY "The location of the Uranium repository")
set(URANIUM_SCRIPTS_DIR "${URANIUM_DIR}/scripts" CACHE DIRECTORY "The location of the scripts directory of the Uranium repository")

# Tests
include(SteSlicerTests)

option(STESLICER_DEBUGMODE "Enable debug dialog and other debug features" OFF)
if(STESLICER_DEBUGMODE)
    set(_steslicer_debugmode "ON")
endif()

set(STESLICER_VERSION "master" CACHE STRING "Version name of STE Slicer")
set(STESLICER_BUILDTYPE "" CACHE STRING "Build type of STE Slicer, eg. 'PPA'")
set(STESLICER_SDK_VERSION "" CACHE STRING "SDK version of STE Slicer")

# configure_file(${CMAKE_SOURCE_DIR}/cura.desktop.in ${CMAKE_BINARY_DIR}/cura.desktop @ONLY)
configure_file(steslicer/SteslicerVersion.py.in SteSlicerVersion.py @ONLY)

if(NOT ${URANIUM_DIR} STREQUAL "")
    set(CMAKE_MODULE_PATH "${URANIUM_DIR}/cmake")
endif()
if(NOT ${URANIUM_SCRIPTS_DIR} STREQUAL "")
    list(APPEND CMAKE_MODULE_PATH ${URANIUM_DIR}/cmake)
    include(UraniumTranslationTools)
    # Extract Strings
    add_custom_target(extract-messages ${URANIUM_SCRIPTS_DIR}/extract-messages ${CMAKE_SOURCE_DIR} steslicer)
    # Build Translations
    CREATE_TRANSLATION_TARGETS()
endif()

find_package(PythonInterp 3.5.0 REQUIRED)

install(DIRECTORY resources
        DESTINATION ${CMAKE_INSTALL_DATADIR}/steslicer)
install(DIRECTORY plugins
        DESTINATION lib${LIB_SUFFIX}/steslicer)
install(FILES steslicer_app.py
        DESTINATION ${CMAKE_INSTALL_BINDIR}
        PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE WORLD_READ WORLD_EXECUTE)
install(DIRECTORY steslicer
        DESTINATION lib${LIB_SUFFIX}/python${PYTHON_VERSION_MAJOR}.${PYTHON_VERSION_MINOR}/site-packages
        FILES_MATCHING PATTERN *.py)
install(FILES ${CMAKE_BINARY_DIR}/SteSlicerVersion.py
        DESTINATION lib${LIB_SUFFIX}/python${PYTHON_VERSION_MAJOR}.${PYTHON_VERSION_MINOR}/site-packages/steslicer)

