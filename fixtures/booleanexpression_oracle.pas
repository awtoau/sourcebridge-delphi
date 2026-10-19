program BooleanExpressionOracle;

function IsGreater(Left: Integer; Right: Integer): Boolean;
begin
  Result := Left > Right;
end;

begin
  Writeln('IsGreater(7,3)=', Ord(IsGreater(7, 3)));
  Writeln('IsGreater(3,7)=', Ord(IsGreater(3, 7)));
  Writeln('IsGreater(5,5)=', Ord(IsGreater(5, 5)));
end.
