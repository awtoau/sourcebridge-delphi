program PasFacts;

{$mode objfpc}{$H+}

// Compiler-grounded Pascal fact extractor using Free Pascal's OWN parser
// (fcl-passrc), as the C# pack uses Roslyn and the C pack uses clang. It walks
// a real AST and emits the function-level fact kinds the Sourcebridge rules
// consume: scalar addition, boolean comparison (branch and expression), and
// string length.

uses
  SysUtils, Classes, PScanner, PParser, PasTree;

type
  TFactEngine = class(TPasTreeContainer)
  public
    function CreateElement(AClass: TPTreeElement; const AName: String;
      AParent: TPasElement; AVisibility: TPasMemberVisibility;
      const ASourceFilename: String; ASourceLinenumber: Integer): TPasElement; override;
    function FindElement(const AName: String): TPasElement; override;
  end;

var
  Facts: TStringList;

function TFactEngine.CreateElement(AClass: TPTreeElement; const AName: String;
  AParent: TPasElement; AVisibility: TPasMemberVisibility;
  const ASourceFilename: String; ASourceLinenumber: Integer): TPasElement;
begin
  Result := AClass.Create(AName, AParent);
  Result.Visibility := AVisibility;
  Result.SourceFilename := ASourceFilename;
  Result.SourceLinenumber := ASourceLinenumber;
end;

function TFactEngine.FindElement(const AName: String): TPasElement;
begin
  Result := nil;
end;

function JsonStr(const S: String): String;
begin
  Result := '"' + StringReplace(StringReplace(S, '\', '\\', [rfReplaceAll]), '"', '\"', [rfReplaceAll]) + '"';
end;

function ScalarType(T: TPasType): String;
var N: String;
begin
  Result := '';
  if T = nil then Exit;
  N := LowerCase(T.Name);
  if (N = 'integer') or (N = 'longint') then Result := 'integer'
  else if (N = 'cardinal') or (N = 'longword') then Result := 'cardinal';
end;

function IsBoolean(T: TPasType): Boolean;
begin
  Result := (T <> nil) and (LowerCase(T.Name) = 'boolean');
end;

function IsString(T: TPasType): Boolean;
begin
  Result := (T <> nil) and (LowerCase(T.Name) = 'string');
end;

function CompareOp(Op: TExprOpCode): String;
begin
  case Op of
    eopEqual: Result := '=';
    eopNotEqual: Result := '<>';
    eopLessThan: Result := '<';
    eopGreaterThan: Result := '>';
    eopLessthanEqual: Result := '<=';
    eopGreaterThanEqual: Result := '>=';
  else
    Result := '';
  end;
end;

// Two simple identifier operands of a binary expression with a given op class.
function BinaryIdents(Expr: TPasExpr; out L, R: String; out Op: TExprOpCode): Boolean;
var Bin: TBinaryExpr;
begin
  Result := False;
  if not (Expr is TBinaryExpr) then Exit;
  Bin := TBinaryExpr(Expr);
  if not (Bin.left is TPrimitiveExpr) or not (Bin.right is TPrimitiveExpr) then Exit;
  if (TPrimitiveExpr(Bin.left).Kind <> pekIdent) or (TPrimitiveExpr(Bin.right).Kind <> pekIdent) then Exit;
  L := TPrimitiveExpr(Bin.left).Value;
  R := TPrimitiveExpr(Bin.right).Value;
  Op := Bin.OpCode;
  Result := True;
end;

// Single statement of a function body (unwrapping a begin/end if needed).
function SingleStatement(Fn: TPasFunction): TPasImplElement;
var Blk: TPasImplBlock;
begin
  Result := nil;
  if (Fn.Body = nil) or (Fn.Body.Body = nil) then Exit;
  Blk := Fn.Body.Body;
  if Blk.Elements.Count = 1 then
    Result := TPasImplElement(Blk.Elements[0]);
end;

function AssignTargetIsResult(Asn: TPasImplAssign; Fn: TPasFunction): Boolean;
var T: String;
begin
  Result := False;
  if not (Asn.left is TPrimitiveExpr) then Exit;
  T := LowerCase(TPrimitiveExpr(Asn.left).Value);
  Result := (T = 'result') or (T = LowerCase(Fn.Name));
end;

function BoolLiteral(Expr: TPasExpr; out V: Boolean): Boolean;
begin
  Result := False;
  if Expr is TBoolConstExpr then
  begin
    V := TBoolConstExpr(Expr).Value;
    Exit(True);
  end;
  if (Expr is TPrimitiveExpr) and (TPrimitiveExpr(Expr).Kind = pekIdent) then
  begin
    if LowerCase(TPrimitiveExpr(Expr).Value) = 'true' then begin V := True; Exit(True); end;
    if LowerCase(TPrimitiveExpr(Expr).Value) = 'false' then begin V := False; Exit(True); end;
  end;
end;

function ParamsJson(FnType: TPasFunctionType; out AllScalarOrString: Boolean): String;
var I: Integer; Arg: TPasArgument; AType: String;
begin
  Result := '';
  AllScalarOrString := True;
  for I := 0 to FnType.Args.Count - 1 do
  begin
    Arg := TPasArgument(FnType.Args[I]);
    AType := ScalarType(Arg.ArgType);
    if AType = '' then
    begin
      if IsString(Arg.ArgType) then AType := 'string'
      else begin AllScalarOrString := False; Exit; end;
    end;
    if Result <> '' then Result := Result + ',';
    Result := Result + '{"name":' + JsonStr(Arg.Name) + ',"type":' + JsonStr(AType) + '}';
  end;
end;

// Length(X) call -> operand name, else ''.
function LengthCallArg(Expr: TPasExpr): String;
var P: TParamsExpr;
begin
  Result := '';
  if not (Expr is TParamsExpr) then Exit;
  P := TParamsExpr(Expr);
  if P.Kind <> pekFuncParams then Exit;
  if not (P.Value is TPrimitiveExpr) then Exit;
  if LowerCase(TPrimitiveExpr(P.Value).Value) <> 'length' then Exit;
  if Length(P.Params) <> 1 then Exit;
  if not (P.Params[0] is TPrimitiveExpr) then Exit;
  Result := TPrimitiveExpr(P.Params[0]).Value;
end;

procedure EmitFunction(Fn: TPasFunction);
var
  FnType: TPasFunctionType;
  RetType, PJson, L, R, LenArg: String;
  AllOk: Boolean;
  Stmt: TPasImplElement;
  Asn: TPasImplAssign;
  IfEl: TPasImplIfElse;
  Op: TExprOpCode;
  TrueV, FalseV: Boolean;
  IfBranch, ElseBranch: TPasImplElement;
begin
  if not (Fn.ProcType is TPasFunctionType) then Exit;
  FnType := TPasFunctionType(Fn.ProcType);
  if FnType.ResultEl = nil then Exit;
  PJson := ParamsJson(FnType, AllOk);
  if not AllOk then Exit;
  Stmt := SingleStatement(Fn);

  // Integer/Cardinal return
  RetType := ScalarType(FnType.ResultEl.ResultType);
  if RetType <> '' then
  begin
    if (Stmt is TPasImplAssign) then
    begin
      Asn := TPasImplAssign(Stmt);
      if AssignTargetIsResult(Asn, Fn) then
      begin
        // scalar addition
        if BinaryIdents(Asn.right, L, R, Op) and (Op = eopAdd) then
          Facts.Add('{"kind":"scalar_addition_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // scalar division (Pascal `div`)
        else if BinaryIdents(Asn.right, L, R, Op) and (Op = eopDiv) then
          Facts.Add('{"kind":"scalar_division_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // scalar multiplication
        else if BinaryIdents(Asn.right, L, R, Op) and (Op = eopMultiply) then
          Facts.Add('{"kind":"scalar_multiplication_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // scalar subtraction
        else if BinaryIdents(Asn.right, L, R, Op) and (Op = eopSubtract) then
          Facts.Add('{"kind":"scalar_subtraction_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // scalar modulo (Pascal `mod`)
        else if BinaryIdents(Asn.right, L, R, Op) and (Op = eopMod) then
          Facts.Add('{"kind":"scalar_modulo_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // scalar bitwise AND (Pascal `and` on integers)
        else if BinaryIdents(Asn.right, L, R, Op) and (Op = eopAnd) then
          Facts.Add('{"kind":"scalar_bitwise_and_function","name":' + JsonStr(Fn.Name) +
            ',"parameters":[' + PJson + '],"return_type":' + JsonStr(RetType) +
            ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}')
        // string length (Integer return, Length(x))
        else
        begin
          LenArg := LengthCallArg(Asn.right);
          if (LenArg <> '') and (RetType = 'integer') then
            Facts.Add('{"kind":"string_length_function","name":' + JsonStr(Fn.Name) +
              ',"parameters":[' + PJson + '],"return_type":"integer"' +
              ',"operands":[' + JsonStr(LenArg) + ',' + JsonStr(LenArg) + ']}');
        end;
      end;
    end;
    Exit;
  end;

  // string length also valid when param is string and Length used; handled above.

  // Boolean return
  if IsBoolean(FnType.ResultEl.ResultType) then
  begin
    // comparison expression: Result := L <op> R
    if (Stmt is TPasImplAssign) then
    begin
      Asn := TPasImplAssign(Stmt);
      if AssignTargetIsResult(Asn, Fn) and BinaryIdents(Asn.right, L, R, Op) and (CompareOp(Op) <> '') then
        Facts.Add('{"kind":"boolean_comparison_expression_function","name":' + JsonStr(Fn.Name) +
          ',"parameters":[' + PJson + '],"return_type":"boolean"' +
          ',"operator":' + JsonStr(CompareOp(Op)) +
          ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']}');
      Exit;
    end;
    // comparison branch: if L<op>R then Result:=True else Result:=False
    if (Stmt is TPasImplIfElse) then
    begin
      IfEl := TPasImplIfElse(Stmt);
      if not BinaryIdents(IfEl.ConditionExpr, L, R, Op) or (CompareOp(Op) = '') then Exit;
      IfBranch := IfEl.IfBranch;
      ElseBranch := IfEl.ElseBranch;
      if (IfBranch is TPasImplAssign) and (ElseBranch is TPasImplAssign) then
        if AssignTargetIsResult(TPasImplAssign(IfBranch), Fn) and AssignTargetIsResult(TPasImplAssign(ElseBranch), Fn) then
          if BoolLiteral(TPasImplAssign(IfBranch).right, TrueV) and BoolLiteral(TPasImplAssign(ElseBranch).right, FalseV) then
            if TrueV and (not FalseV) then
              Facts.Add('{"kind":"boolean_comparison_branch_function","name":' + JsonStr(Fn.Name) +
                ',"parameters":[' + PJson + '],"return_type":"boolean"' +
                ',"operator":' + JsonStr(CompareOp(Op)) +
                ',"operands":[' + JsonStr(L) + ',' + JsonStr(R) + ']' +
                ',"true_value":true,"false_value":false}');
    end;
  end;
end;

function JoinList(L: TStringList): String;
var I: Integer;
begin
  Result := '';
  for I := 0 to L.Count - 1 do
  begin
    if I > 0 then Result := Result + ',';
    Result := Result + L[I];
  end;
end;

function RustIntName(T: TPasType): String;
var N: String;
begin
  Result := '';
  if T = nil then Exit;
  N := LowerCase(T.Name);
  if (N='byte') or (N='shortint') or (N='smallint') or (N='word')
     or (N='longint') or (N='longword') or (N='cardinal') or (N='integer')
     or (N='int64') or (N='qword') then Result := N;
end;

function NumberLiteral(Expr: TPasExpr; out V: String): Boolean;
begin
  Result := False;
  if Expr = nil then Exit;
  if (Expr is TPrimitiveExpr) and (TPrimitiveExpr(Expr).Kind = pekNumber) then
  begin V := TPrimitiveExpr(Expr).Value; Exit(True); end;
  if (Expr is TUnaryExpr) and (TUnaryExpr(Expr).OpCode = eopSubtract) then
    if (TUnaryExpr(Expr).Operand is TPrimitiveExpr)
       and (TPrimitiveExpr(TUnaryExpr(Expr).Operand).Kind = pekNumber) then
    begin V := '-' + TPrimitiveExpr(TUnaryExpr(Expr).Operand).Value; Exit(True); end;
end;

function BitwiseOpName(Op: TExprOpCode): String;
begin
  case Op of
    eopOr: Result := 'or';
    eopXor: Result := 'xor';
    eopAnd: Result := 'and';
    eopAdd: Result := 'add';
    eopSubtract: Result := 'sub';
    eopMultiply: Result := 'mul';
    eopDiv: Result := 'div';
    eopMod: Result := 'mod';
    eopShl: Result := 'shl';
    eopShr: Result := 'shr';
  else
    Result := '';
  end;
end;

function IdentName(Expr: TPasExpr; out N: String): Boolean;
begin
  Result := False;
  if (Expr is TPrimitiveExpr) and (TPrimitiveExpr(Expr).Kind = pekIdent) then
  begin N := TPrimitiveExpr(Expr).Value; Exit(True); end;
end;

function CallName(Expr: TPasExpr; out Nm: String; out P: TParamsExpr): Boolean;
begin
  Result := False;
  P := nil;
  if not (Expr is TParamsExpr) then Exit;
  P := TParamsExpr(Expr);
  if P.Kind <> pekFuncParams then Exit;
  if not (P.Value is TPrimitiveExpr) then Exit;
  if TPrimitiveExpr(P.Value).Kind <> pekIdent then Exit;
  Nm := LowerCase(TPrimitiveExpr(P.Value).Value);
  Result := True;
end;

procedure WalkDeclarations(Decls: TPasDeclarations);
var I: Integer; El: TPasElement;
begin
  if Decls = nil then Exit;
  for I := 0 to Decls.Declarations.Count - 1 do
  begin
    El := TPasElement(Decls.Declarations[I]);
    if El is TPasFunction then EmitFunction(TPasFunction(El));
  end;
end;

// Program main-block statement inventory: one structured record per statement,
// marking anything the current rules cannot port as "unported" so the emitter
// can degrade gracefully while still producing runnable Rust.
procedure WalkProgramBody(Prog: TPasProgram);
var
  I: Integer; El: TPasElement; V: TPasVariable; TName: String;
  Vars, Stmts: TStringList;
  Blk: TPasImplBlock; Stmt: TPasImplElement;
  Asn: TPasImplAssign; IfEl: TPasImplIfElse;
  Target, L, R, Num, CmpOp, HaltCode, CName, ArgN, HName: String;
  P, HP: TParamsExpr; Branch: TPasImplElement;
begin
  if Prog.InitializationSection = nil then Exit;
  Vars := TStringList.Create;
  Stmts := TStringList.Create;
  try
    if Prog.ProgramSection <> nil then
      for I := 0 to Prog.ProgramSection.Declarations.Count - 1 do
      begin
        El := TPasElement(Prog.ProgramSection.Declarations[I]);
        if El is TPasVariable then
        begin
          V := TPasVariable(El);
          TName := RustIntName(V.VarType);
          if TName <> '' then
            Vars.Add('{"name":' + JsonStr(V.Name) + ',"type":' + JsonStr(TName) + '}');
        end;
      end;
    Blk := Prog.InitializationSection;
    for I := 0 to Blk.Elements.Count - 1 do
    begin
      Stmt := TPasImplElement(Blk.Elements[I]);
      if Stmt is TPasImplAssign then
      begin
        Asn := TPasImplAssign(Stmt);
        if not IdentName(Asn.left, Target) then
          Stmts.Add('{"stmt":"unported","note":"non-ident assignment target"}')
        else if NumberLiteral(Asn.right, Num) then
          Stmts.Add('{"stmt":"assign_const","target":' + JsonStr(Target) +
            ',"value":' + JsonStr(Num) + '}')
        else if (Asn.right is TBinaryExpr)
             and IdentName(TBinaryExpr(Asn.right).left, L)
             and IdentName(TBinaryExpr(Asn.right).right, R)
             and (BitwiseOpName(TBinaryExpr(Asn.right).OpCode) <> '') then
          Stmts.Add('{"stmt":"assign_binary","target":' + JsonStr(Target) +
            ',"op":' + JsonStr(BitwiseOpName(TBinaryExpr(Asn.right).OpCode)) +
            ',"left":' + JsonStr(L) + ',"right":' + JsonStr(R) + '}')
        else
          Stmts.Add('{"stmt":"unported","note":"unsupported assignment rhs"}');
      end
      else if Stmt is TPasImplSimple then
      begin
        if CallName(TPasImplSimple(Stmt).Expr, CName, P) then
        begin
          if ((CName='writeln') or (CName='write')) and (Length(P.Params)=1)
             and IdentName(P.Params[0], ArgN) then
            Stmts.Add('{"stmt":"writeln","arg":' + JsonStr(ArgN) + '}')
          else
            Stmts.Add('{"stmt":"unported","note":' + JsonStr('call ' + CName) + '}');
        end
        else
          Stmts.Add('{"stmt":"unported","note":"non-call simple statement"}');
      end
      else if Stmt is TPasImplIfElse then
      begin
        IfEl := TPasImplIfElse(Stmt);
        CmpOp := '';
        if (IfEl.ConditionExpr is TBinaryExpr)
           and IdentName(TBinaryExpr(IfEl.ConditionExpr).left, L)
           and NumberLiteral(TBinaryExpr(IfEl.ConditionExpr).right, Num) then
          CmpOp := CompareOp(TBinaryExpr(IfEl.ConditionExpr).OpCode);
        Branch := IfEl.IfBranch;
        if (CmpOp <> '') and (Branch is TPasImplSimple)
           and CallName(TPasImplSimple(Branch).Expr, HName, HP)
           and (HName='halt') and (Length(HP.Params)=1)
           and NumberLiteral(HP.Params[0], HaltCode) then
          Stmts.Add('{"stmt":"if_halt","left":' + JsonStr(L) + ',"op":' + JsonStr(CmpOp) +
            ',"right":' + JsonStr(Num) + ',"code":' + JsonStr(HaltCode) + '}')
        else
          Stmts.Add('{"stmt":"unported","note":"unsupported if statement"}');
      end
      else
        Stmts.Add('{"stmt":"unported","note":"unsupported statement kind"}');
    end;
    Facts.Add('{"kind":"program_body","name":' + JsonStr(Prog.Name) +
      ',"variables":[' + JoinList(Vars) + '],"statements":[' + JoinList(Stmts) + ']}');
  finally
    Vars.Free;
    Stmts.Free;
  end;
end;

var
  Engine: TFactEngine;
  Module: TPasModule;
  FileName: String;
  WantProgramBody: Boolean;
  I: Integer;
begin
  if ParamCount < 1 then begin Writeln(StdErr, 'usage: pasfacts <source.pp> [--program-body]'); Halt(2); end;
  FileName := ParamStr(1);
  WantProgramBody := False;
  for I := 2 to ParamCount do
    if ParamStr(I) = '--program-body' then WantProgramBody := True;
  Facts := TStringList.Create;
  Engine := TFactEngine.Create;
  try
    try
      Module := ParseSource(Engine, FileName, 'x86_64', 'linux');
    except
      on E: Exception do
      begin
        Writeln('{"parsed":false,"error":', JsonStr(E.Message), '}');
        Halt(1);
      end;
    end;
    if Module is TPasProgram then
    begin
      WalkDeclarations(TPasProgram(Module).ProgramSection);
      if WantProgramBody then WalkProgramBody(TPasProgram(Module));
    end
    else
    begin
      WalkDeclarations(Module.InterfaceSection);
      WalkDeclarations(Module.ImplementationSection);
    end;
    Write('{"parsed":true,"source_path":', JsonStr(FileName), ',"facts":[');
    for I := 0 to Facts.Count - 1 do
    begin
      if I > 0 then Write(',');
      Write(Facts[I]);
    end;
    Writeln(']}');
  finally
    Engine.Free;
    Facts.Free;
  end;
end.
