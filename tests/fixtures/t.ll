; Fixture IR for function _Z3foov
define dso_local void @_Z3foov() #0 {
entry:
  br label %for.cond
for.cond:
  br i1 true, label %for.body, label %for.end
for.body:
  br label %for.cond
for.end:
  ret void
}
