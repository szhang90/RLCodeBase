for r in `seq 30 99`
do
  python officeNavigation.py -n 5 -r $r
  python officeNavigation.py -n 10 -r $r
  python officeNavigation.py -n 15 -r $r
done

