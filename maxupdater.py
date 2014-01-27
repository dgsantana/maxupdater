#!/usr/bin/python2.7
__author__ = 'Daniel Santana'

from MaxUpdaterService import MaxUpdaterService

if __name__ == '__main__':
    s = MaxUpdaterService()
    s.standalone_loop()