program StringLengthOracle;

function TextLength(Value: String): Integer;
begin
  Result := Length(Value);
end;

begin
  Writeln('TextLength(hello)=', TextLength('hello'));
  Writeln('TextLength(empty)=', TextLength(''));
  Writeln('TextLength(abcde)=', TextLength('abcde'));
end.
