for i in `seq 10 29`
do
  echo $i
  python drivingExp.py -r $i -a OPT-POLICY
  python drivingExp.py -r $i -a MILP-SIMILAR -t 2
  python drivingExp.py -r $i -a MILP-SIMILAR -t 3
  python drivingExp.py -r $i -a MILP-SIMILAR -t 4
  python drivingExp.py -r $i -a MILP-SIMILAR -t 5
  python drivingExp.py -r $i -a MILP-SIMILAR-NAIVE -t 2
  python drivingExp.py -r $i -a MILP-SIMILAR-NAIVE -t 3
  python drivingExp.py -r $i -a MILP-SIMILAR-NAIVE -t 4
  python drivingExp.py -r $i -a MILP-SIMILAR-NAIVE -t 5
done

