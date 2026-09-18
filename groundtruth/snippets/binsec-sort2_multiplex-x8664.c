void sort2_multiplex(int *out2, int *in2) {
  signed char c;
  c = (in2[0] < in2[1]) - 1;
  out2[0] = (~c & in2[0]) | (c & in2[1]);
  out2[1] = (~c & in2[1]) | (c & in2[0]);
  return;
}