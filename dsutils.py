from glob import iglob
from shutil import copy
from os import makedirs, remove
from os.path import join, dirname, exists, basename


def copy_files(src_glob, dst_folder, logger):
    """
    Copy files using wildcards
    """
    counter = 0
    for fname in iglob(src_glob):
        try:
            copy(fname, join(dst_folder, basename(fname)))
        except:
            logger.error('Failed to copy %s' % fname)
            continue
        counter += 1
    return counter


def delete_files(src_glob, logger):
    """
    Delete files using wildcards
    """
    for fname in iglob(src_glob):
        if exists(fname):
            try:
                remove(fname)
            except:
                logger.error('Failed to delete %s' % fname)


def GetHashofDirs(directory, verbose=0, ignore=[]):
    import hashlib, os

    SHAhash = hashlib.sha1()
    if not os.path.exists(directory):
        return -1

    try:

        for root, dirs, files in os.walk(directory):
            for names in files:
                if verbose == 1:
                    print 'Hashing', names
                filepath = os.path.join(root, names)
                if 'backup.id' in names:
                    continue
                try:
                    f1 = open(filepath, 'rb')
                except:
                    # You can't open the file for some reason
                    f1.close()
                    continue

                while 1:
                    # Read file in as little chunks
                    buf = f1.read(4096)
                    if not buf:
                        break
                    SHAhash.update(hashlib.sha1(buf).hexdigest())
                f1.close()

    except:
        import traceback
        # Print the stack traceback
        traceback.print_exc()
        return -2

    return SHAhash.hexdigest()