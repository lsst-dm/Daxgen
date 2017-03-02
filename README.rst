Daxgen
------

An (very) early prototype of the workflow generator for Batch Production
Services.


Prerequisites
-------------

``Daxgen`` depends on the following third-party software packages:

* `Jinja2 <http://jinja.pocoo.org/>`_ (>=2.9),
* `Pegasus <http:://pegasus.isi.edu/>`_ (>=4.7).
* `AutoADAG.py <https://github.com/pegasus-isi/pegasus-gtfar/blob/1.0/pegasus/gtfar/dax/AutoADAG.py>`_

As we are concerned with workflow representing LSST scientific pipelines to be
used with the LSST Batch Production Services, you will also have need

* `The LSST Stack <https://github.com/lsst/lsstsw>`_,
* `Executor <https://github.com/lsst-dm/Executor>`_.

Setting things up
-----------------

lsst-dev
========

Firstly, let's make Pegasus binaries and its Python components available in the
working shell:

.. code-block::

   $ export PEGASUSHOME=/software/middleware/pegasus/pegasus-4.7.2-1/usr
   $ export PATH=${PEGASUSHOME}/bin:$PATH
   $ export PYTHONPATH=${PEGASUSHOME}/lib64/python2.7/site-packages/:$PYTHONPATH

Then, let's setup the LSST Stack:

.. code-block::

   $ source /software/lsstsw/stack/loadLSST.bash
   $ setup -v ctrl_platform_lsstvc
   $ setup -k -v -r /scratch/hchiang2/sw/ci_hsc/

and install the ``Executor``:

.. code-block::

   $ export PYTHONPATH="$PYTHONPATH:$DIR/Executor"
   $ export PATH="$PATH:$DIR/Executor/bin"

where ``$DIR`` is the directory you've cloned its repository to and append

.. code-block::

   tr execute {
       site lsstvc {
           pfn "$DIR/Executor/bin/execute"
           arch "x86_64"
           os "linux"
           type "INSTALLED"
       }
   }

to Pegasus transformation catalog, ``tc.txt``.

Finally, clone project's repository to a preferred location

.. code-block::

   git clone https://github.com/lsst-dm/Daxgen.git

and place ``AutoADAG.py`` in the package (i.e. in ``daxgen``).

Running the worfklow
--------------------

To run the workflow, firstly we have to generate its representation in the
format understandable by Pegasus:

.. code-block::

   $ python daxgen/generate_dax.py input.yaml

The above command should generate the file ``simple.dax`` and a bunch of
scripts in JSON format telling Executor how to run tasks the workflow consists
of.  However, before we can actually execute the workflow, there is one more
things to do -- allocating required computational resources.

Pegasus is using internally `HTCondor`_ to distribute work among available
computational resources. We can allocate required number of nodes using
``allocateNodes.py`` for an fixed amount of time as shown below

.. code-block::

   $ allocateNodes.py -n 1 -s 2 -m 01:00:00 lsstvc
   mxk_1

Here, we allocated a single node with two slots for an hour.

After successful allocation the above command should return a handle to the
allocated set of nodes (here ``mxk_1``) which we store in an environmental
variable

.. code-block::
   
   $ export NODESET='mxk_1'

Now we can ask Pegasus to run the workflow prepared earlier

.. code-block::

   $ ./plan_dax.sh simple.dax

.. _HTCondor: https://research.cs.wisc.edu/htcondor/
